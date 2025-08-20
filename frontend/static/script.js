// Flow timings: wait 3s after video end to show welcome, then 3s to registration
const introVideo = document.getElementById("intro-video");
const introScreen = document.getElementById("intro-screen");
const appMain = document.getElementById("app");
const welcome = document.getElementById("welcome");
const registration = document.getElementById("registration");
const quiz = document.getElementById("quiz");
const thank = document.getElementById("thank");

const registerBtn = document.getElementById("register-btn");
const startBtn = document.getElementById("start-btn");
const regStatus = document.getElementById("reg-status");

// quiz header elements
const qTitle = document.getElementById("q-title");
const qCount = document.getElementById("q-count");
const progressFill = document.getElementById("progress-fill");

// sidebar nav
const navItems = document.querySelectorAll('.nav .item');
function setActiveNav(key){
  const map = { home:0, registration:1, quiz:2, leaderboard:3 };
  const idx = map[key];
  navItems.forEach((el,i)=>{
    if(i===idx) el.classList.add('active'); else el.classList.remove('active');
  });
}

// user badge elements
const userBadge = document.getElementById("user-badge");
const ubName = document.getElementById("ub-name");
const ubRegno = document.getElementById("ub-regno");
const ubAvatar = document.getElementById("ub-avatar");
const ubClear = document.getElementById("ub-clear");

// Clear stored user on hard refresh (F5/Ctrl+R)
try{
  let isReload = false;
  const navEntries = (performance.getEntriesByType && performance.getEntriesByType("navigation")) || [];
  if(navEntries[0] && navEntries[0].type === "reload") isReload = true;
  // legacy fallback
  if(!isReload && performance && performance.navigation && performance.navigation.type === 1) isReload = true;
  if(isReload){
    localStorage.removeItem("quiz_user");
  }
}catch{}

// user state
let QUESTIONS = [];
let currentIndex = 0;
let timerInt = null;
const PER_TIME = 60; // 1 minute per question
let timeLeft = PER_TIME;
let answersGiven = [];
let questionStartTime = null;
let userName = "", userRegno = "";

function showUserBadge(name, regno){
  if(name && regno){
    ubName.textContent = name;
    ubRegno.textContent = regno;
    ubAvatar.textContent = (name?.[0] || 'U').toUpperCase();
    userBadge.classList.remove("hidden");
  } else {
    userBadge.classList.add("hidden");
  }
}

function clearUser(){
  try { localStorage.removeItem("quiz_user"); } catch {}
  userName = ""; userRegno = "";
  showUserBadge("", "");
}

ubClear?.addEventListener('click', clearUser);

function restoreUserFromStorage(){
  const s = localStorage.getItem("quiz_user");
  if(s){
    try{
      const obj = JSON.parse(s);
      userName = obj.name || "";
      userRegno = obj.regno || "";
      showUserBadge(userName, userRegno);
    }catch{ /* ignore */ }
  } else {
    showUserBadge("", "");
  }
}

// get questions from server
async function fetchQuestions(){
  const res = await fetch("/questions");
  QUESTIONS = await res.json();
}

// restore on initial script load
restoreUserFromStorage();

// video end -> show welcome after 3s

// Reduce intro video to 2 seconds: skip to end after 2s if not already ended
let introTimeout = setTimeout(() => {
  if (!introVideo.ended) {
    introVideo.currentTime = introVideo.duration || 9999; // force end
    introVideo.dispatchEvent(new Event("ended"));
  }
}, 2000);

introVideo.addEventListener("ended", async () => {
  clearTimeout(introTimeout);
  // hide intro visuals
  introScreen.style.display = "none";
  // allow app visibility
  appMain.removeAttribute("aria-hidden");

  // show welcome
  welcome.classList.remove("hidden");
  setActiveNav('home');
  // after 3s show registration
  setTimeout(() => {
    welcome.classList.add("hidden");
    registration.classList.remove("hidden");
    document.getElementById("name").focus();
    setActiveNav('registration');
  }, 3000);

  // preload questions
  fetchQuestions();
});

// register handler
registerBtn.addEventListener("click", async () => {
  const name = document.getElementById("name").value.trim();
  const regno = document.getElementById("regno").value.trim();
  const college = document.getElementById("college").value.trim();
  const department = document.getElementById("department").value.trim();
  const year = document.getElementById("year").value.trim();

  if(!name || !regno){
    regStatus.textContent = "Name and Reg No are required.";
    return;
  }

  registerBtn.disabled = true;
  regStatus.textContent = "Registering...";

  try {
    const res = await fetch("/register", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({name, regno, college, department, year})
    });
    const j = await res.json();
    if(j.success){
      // prefer server-echoed values
      userName = j.name || name; 
      userRegno = j.regno || regno;
      // persist for navigation / reloads
      try { localStorage.setItem("quiz_user", JSON.stringify({name: userName, regno: userRegno})); } catch {}
      showUserBadge(userName, userRegno);

      regStatus.textContent = "Registered successfully.";
      startBtn.classList.remove("hidden");
      startBtn.classList.add("slide-in");
    } else {
      regStatus.textContent = j.message || "Registration failed.";
    }
  } catch (e) {
    regStatus.textContent = "Network error.";
  } finally {
    registerBtn.disabled = false;
  }
});

// start quiz handler
startBtn.addEventListener("click", () => {
  registration.classList.add("hidden");
  quiz.classList.remove("hidden");
  currentIndex = 0; answersGiven = [];
  showUserBadge(userName, userRegno);
  showQuestion();
  startTimer();
  setActiveNav('quiz');
});

// show question
function showQuestion(){
  if(currentIndex >= QUESTIONS.length){
    finishQuiz();
    return;
  }
  const q = QUESTIONS[currentIndex];
  // header info
  qTitle.textContent = "Question";
  qCount.textContent = `Q ${currentIndex+1} of ${QUESTIONS.length}`;
  const pct = Math.round(((currentIndex) / Math.max(1, QUESTIONS.length)) * 100);
  if(progressFill) progressFill.style.width = pct + "%";
  document.getElementById("question-text").innerText = `Q${currentIndex+1}. ${q.question}`;
  const opts = document.getElementById("options");
  opts.innerHTML = "";
  q.options.forEach((o, idx) => {
    const d = document.createElement("div");
    d.className = "option";
    d.innerText = o;
    d.onclick = () => {
      document.querySelectorAll(".option").forEach(x=>x.classList.remove("selected"));
      d.classList.add("selected");
      // store answer for this question in memory (overwrite if reselect)
      answersGiven[currentIndex] = {qId: q.id ?? currentIndex, selected: idx, time_sec: getQuestionTime()};
    };
    opts.appendChild(d);
  });

  // UI animation
  const qbox = document.getElementById("question-box");
  qbox.classList.remove("slide-in");
  void qbox.offsetWidth;
  qbox.classList.add("slide-in");

  // reset timer
  timeLeft = PER_TIME;
  document.getElementById("time").innerText = timeLeft;
  questionStartTime = Date.now();
}

function getQuestionTime(){
  if(!questionStartTime) return PER_TIME;
  const elapsed = Math.round((Date.now() - questionStartTime)/1000);
  return Math.min(elapsed, PER_TIME);
}

// timer
function startTimer(){
  clearInterval(timerInt);
  timeLeft = PER_TIME;
  document.getElementById("time").innerText = timeLeft;
  timerInt = setInterval(() => {
    timeLeft--;
    document.getElementById("time").innerText = timeLeft;
  // animate progress for time within current question
  const elapsedPct = Math.max(0, Math.min(100, ((PER_TIME - timeLeft) / PER_TIME) * (100/Math.max(1, QUESTIONS.length))));
  const basePct = ((currentIndex) / Math.max(1, QUESTIONS.length)) * 100;
  if(progressFill) progressFill.style.width = (basePct + elapsedPct) + "%";
    if(timeLeft <= 0){
      clearInterval(timerInt);
      nextQuestion();
    }
  }, 1000);
}

// next question
document.getElementById("next-btn").addEventListener("click", nextQuestion);
function nextQuestion(){
  clearInterval(timerInt);
  // if no selection for this question, store null and time
  if(!answersGiven[currentIndex]) answersGiven[currentIndex] = {qId: QUESTIONS[currentIndex].id ?? currentIndex, selected: null, time_sec: getQuestionTime()};
  currentIndex++;
  if(currentIndex < QUESTIONS.length){
    showQuestion();
    startTimer();
  } else {
    finishQuiz();
  }
}

// finish quiz: compute score locally using questions.json answers (server has answers too)
async function finishQuiz(){
  clearInterval(timerInt);
  // Build payload with timings
  const payload = { name: userName, regno: userRegno, answers: answersGiven };
  try {
    const res = await fetch("/submit-quiz", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(payload)
    });
    const j = await res.json();
    if(j.success){
      quiz.classList.add("hidden");
      thank.classList.remove("hidden");
      document.getElementById("final-msg").innerHTML = `Your quiz has been submitted.`;
      // Show leaderboard after short delay
      setTimeout(showLeaderboard, 1200);
    } else {
      alert("Error submitting quiz: " + (j.message || "unknown"));
    }
  } catch (err) {
    alert("Network error sending results.");
  }
}

async function showLeaderboard(){
  thank.classList.add("hidden");
  const lbSection = document.getElementById("leaderboard");
  lbSection.classList.remove("hidden");
  setActiveNav('leaderboard');
  const tableDiv = document.getElementById("leaderboard-table");
  tableDiv.innerHTML = "Loading...";
  let yourRank = "";
  try {
    const res = await fetch("/api/leaderboard");
    const data = await res.json();
    if(Array.isArray(data)){
      // Only show Rank, Reg No, Points, Avg Time
      let html = `<div class='lb-card'><table class='lb-table'><thead><tr><th>Rank</th><th>Reg No</th><th>Points</th><th>Avg Time (s)</th></tr></thead><tbody>`;
      let found = false;
      data.forEach((row, idx) => {
        const avgTime = row.avg_time ?? "";
        const highlight = row.regno===userRegno ? " class='highlight'" : "";
        html += `<tr${highlight}><td>${idx+1}</td><td>${row.regno}</td><td>${row.points}</td><td>${avgTime}</td></tr>`;
        if(row.regno===userRegno){
          yourRank = `Your Rank: ${idx+1} | Points: ${row.points} | Avg Time: ${avgTime}s`;
          found = true;
        }
      });
      html += `</tbody></table></div>`;
      tableDiv.innerHTML = html;
      document.getElementById("your-rank").textContent = yourRank || "You are not ranked yet.";
    } else {
      tableDiv.innerHTML = "No leaderboard data.";
    }
  } catch(e){
    tableDiv.innerHTML = "Error loading leaderboard.";
  }
}

document.getElementById("close-leaderboard").addEventListener("click", () => {
  document.getElementById("leaderboard").classList.add("hidden");
  // Optionally show welcome or registration again
  welcome.classList.remove("hidden");
});
function sendResultToServer(playerName, score, totalQuestions, timeTakenSec, answers) {
  fetch('/submit_result', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: playerName,
      score: score,
      total: totalQuestions,
      time_taken: timeTakenSec,
      answers: answers // array of {question, selected, correct}
    })
  })
  .then(res => res.json())
  .then(data => {
    console.log('Result saved:', data);
    // window.location.href = '/leaderboard.html';
    showLeaderboard(); // Show the primary leaderboard directly
  })
  .catch(err => console.error('Error saving result:', err));
}

