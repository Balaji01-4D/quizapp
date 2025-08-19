import os
import json
import tempfile
import unittest
from unittest.mock import patch
from io import StringIO
import base64

# Set test environment before importing app
os.environ['DB_URL'] = 'sqlite:///:memory:'
os.environ['ADMIN_USERNAME'] = 'testadmin'
os.environ['ADMIN_PASSWORD'] = 'testpass123'

from app import app, QUESTIONS_FILE
from models import db, Participant, Result, Answer


class QuizAppTestCase(unittest.TestCase):
    
    def setUp(self):
        """Set up test client and in-memory database"""
        self.app = app.test_client()
        self.app.testing = True
        
        # Create temporary questions file
        self.temp_questions = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        self.test_questions = [
            {
                "question": "What is 2+2?",
                "options": ["3", "4", "5", "6"],
                "answer": 1
            },
            {
                "question": "What is the capital of France?",
                "options": ["London", "Berlin", "Paris", "Madrid"],
                "answer": 2
            }
        ]
        json.dump(self.test_questions, self.temp_questions)
        self.temp_questions.close()
        
        # Patch QUESTIONS_FILE to point to temp file
        import app as app_module
        from pathlib import Path
        self.questions_patcher = patch.object(app_module, 'QUESTIONS_FILE', Path(self.temp_questions.name))
        self.questions_patcher.start()
        
        # Setup test database
        db.drop_tables([Answer, Result, Participant], safe=True)
        db.create_tables([Participant, Result, Answer], safe=True)
        
        # Create test data
        self.test_participant = Participant.create(
            name="Test User",
            regno="TEST001",
            college="Test College",
            dept="Computer Science",
            year=2023
        )
        self.test_result = Result.create(
            participant=self.test_participant,
            correct=1,
            points=2,
            avg_time=15.5
        )
    
    def tearDown(self):
        """Clean up after tests"""
        self.questions_patcher.stop()
        os.unlink(self.temp_questions.name)
        db.drop_tables([Answer, Result, Participant], safe=True)
    
    def get_basic_auth_headers(self, username='testadmin', password='testpass123'):
        """Generate Basic Auth headers"""
        credentials = base64.b64encode(f'{username}:{password}'.encode()).decode()
        return {'Authorization': f'Basic {credentials}'}
    
    def test_index_route(self):
        """Test the main index page"""
        response = self.app.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Algorithm Quiz', response.data)
    
    def test_register_success(self):
        """Test successful user registration"""
        data = {
            "name": "New User",
            "regno": "NEW001",
            "college": "New College",
            "department": "Engineering",
            "year": "2024"
        }
        response = self.app.post('/register', 
                                json=data,
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        json_data = json.loads(response.data)
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['name'], "New User")
        self.assertEqual(json_data['regno'], "NEW001")
        
        # Verify participant was created
        participant = Participant.get_or_none(Participant.regno == "NEW001")
        self.assertIsNotNone(participant)
        self.assertEqual(participant.name, "New User")
    
    def test_register_missing_fields(self):
        """Test registration with missing fields"""
        data = {
            "name": "Incomplete User",
            "regno": "INC001"
            # Missing college, department, year
        }
        response = self.app.post('/register',
                                json=data,
                                content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        json_data = json.loads(response.data)
        self.assertFalse(json_data['success'])
        self.assertIn('Missing fields', json_data['message'])
    
    def test_register_duplicate_regno(self):
        """Test registration with duplicate regno"""
        data = {
            "name": "Duplicate User",
            "regno": "TEST001",  # Already exists
            "college": "Test College",
            "department": "CS",
            "year": "2023"
        }
        response = self.app.post('/register',
                                json=data,
                                content_type='application/json')
        self.assertEqual(response.status_code, 409)
        
        json_data = json.loads(response.data)
        self.assertFalse(json_data['success'])
        self.assertIn('already exists', json_data['message'])
    
    def test_register_invalid_year(self):
        """Test registration with invalid year"""
        data = {
            "name": "Invalid Year User",
            "regno": "INV001",
            "college": "Test College",
            "department": "CS",
            "year": "not_a_number"
        }
        response = self.app.post('/register',
                                json=data,
                                content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        json_data = json.loads(response.data)
        self.assertFalse(json_data['success'])
        self.assertIn('must be a number', json_data['message'])
    
    def test_get_questions(self):
        """Test getting quiz questions"""
        response = self.app.get('/questions')
        self.assertEqual(response.status_code, 200)
        
        questions = json.loads(response.data)
        self.assertEqual(len(questions), 2)
        self.assertIn('question', questions[0])
        self.assertIn('options', questions[0])
        self.assertNotIn('answer', questions[0])  # Answer should be hidden
    
    def test_submit_quiz_success(self):
        """Test successful quiz submission"""
        answers = [
            {"qId": 0, "selected": 1, "time_sec": 10},
            {"qId": 1, "selected": 2, "time_sec": 15}
        ]
        data = {
            "name": "Test User",
            "regno": "TEST001",
            "answers": answers
        }
        response = self.app.post('/submit-quiz',
                                json=data,
                                content_type='application/json')
        self.assertEqual(response.status_code, 200)
        
        json_data = json.loads(response.data)
        self.assertTrue(json_data['success'])
        
        # Verify result was updated
        result = Result.get(Result.participant == self.test_participant)
        self.assertEqual(result.correct, 2)  # Both answers correct
        self.assertEqual(result.points, 4)   # 2 points per correct
    
    def test_submit_quiz_unregistered_user(self):
        """Test quiz submission from unregistered user"""
        data = {
            "name": "Unknown User",
            "regno": "UNKNOWN001",
            "answers": []
        }
        response = self.app.post('/submit-quiz',
                                json=data,
                                content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        json_data = json.loads(response.data)
        self.assertFalse(json_data['success'])
        self.assertIn('register first', json_data['message'])
    
    def test_submit_quiz_no_data(self):
        """Test quiz submission with no data"""
        response = self.app.post('/submit-quiz')
        # Expect 415 (Unsupported Media Type) when no content-type header is provided
        self.assertEqual(response.status_code, 415)
    
    def test_leaderboard_route(self):
        """Test leaderboard HTML page"""
        response = self.app.get('/leaderboard')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Leaderboard', response.data)
        self.assertIn(b'Test User', response.data)
    
    def test_api_leaderboard(self):
        """Test leaderboard JSON API"""
        response = self.app.get('/api/leaderboard')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn('name', data[0])
        self.assertIn('points', data[0])
    
    def test_admin_without_auth(self):
        """Test admin route without authentication"""
        response = self.app.get('/admin')
        self.assertEqual(response.status_code, 401)
    
    def test_admin_with_wrong_auth(self):
        """Test admin route with wrong credentials"""
        headers = self.get_basic_auth_headers('wrong', 'credentials')
        response = self.app.get('/admin', headers=headers)
        self.assertEqual(response.status_code, 401)
    
    def test_admin_dashboard(self):
        """Test admin dashboard with correct auth"""
        headers = self.get_basic_auth_headers()
        response = self.app.get('/admin', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Admin Dashboard', response.data)
        self.assertIn(b'Test User', response.data)
    
    def test_admin_api_top(self):
        """Test admin API for top participants"""
        headers = self.get_basic_auth_headers()
        response = self.app.get('/admin/api/top', headers=headers)
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)
        self.assertIn('rank', data[0])
        self.assertIn('name', data[0])
    
    def test_admin_delete_participant_success(self):
        """Test successful participant deletion"""
        headers = self.get_basic_auth_headers()
        data = {"regno": "TEST001"}
        response = self.app.post('/admin/api/delete-participant',
                                json=data,
                                content_type='application/json',
                                headers=headers)
        self.assertEqual(response.status_code, 200)
        
        json_data = json.loads(response.data)
        self.assertTrue(json_data['success'])
        
        # Verify participant was deleted
        participant = Participant.get_or_none(Participant.regno == "TEST001")
        self.assertIsNone(participant)
    
    def test_admin_delete_participant_not_found(self):
        """Test deletion of non-existent participant"""
        headers = self.get_basic_auth_headers()
        data = {"regno": "NONEXISTENT"}
        response = self.app.post('/admin/api/delete-participant',
                                json=data,
                                content_type='application/json',
                                headers=headers)
        self.assertEqual(response.status_code, 404)
        
        json_data = json.loads(response.data)
        self.assertFalse(json_data['success'])
    
    def test_admin_delete_participant_missing_regno(self):
        """Test deletion without regno"""
        headers = self.get_basic_auth_headers()
        data = {}
        response = self.app.post('/admin/api/delete-participant',
                                json=data,
                                content_type='application/json',
                                headers=headers)
        self.assertEqual(response.status_code, 400)
        
        json_data = json.loads(response.data)
        self.assertFalse(json_data['success'])
        self.assertIn('regno required', json_data['message'])
    
    def test_admin_add_question_success(self):
        """Test successful question addition"""
        headers = self.get_basic_auth_headers()
        data = {
            "question": "What is 3+3?",
            "options": ["5", "6", "7", "8"],
            "answer": 1
        }
        response = self.app.post('/admin/api/add-question',
                                json=data,
                                content_type='application/json',
                                headers=headers)
        self.assertEqual(response.status_code, 200)
        
        json_data = json.loads(response.data)
        self.assertTrue(json_data['success'])
        self.assertEqual(json_data['count'], 3)  # Original 2 + new 1
        
        # Verify question was added to file
        with open(self.temp_questions.name, 'r') as f:
            questions = json.load(f)
        self.assertEqual(len(questions), 3)
        self.assertEqual(questions[2]['question'], "What is 3+3?")
    
    def test_admin_add_question_invalid_data(self):
        """Test adding question with invalid data"""
        headers = self.get_basic_auth_headers()
        
        # Test missing question
        data = {"options": ["A", "B"], "answer": 0}
        response = self.app.post('/admin/api/add-question',
                                json=data,
                                content_type='application/json',
                                headers=headers)
        self.assertEqual(response.status_code, 400)
        
        # Test invalid options
        data = {"question": "Test?", "options": ["A"], "answer": 0}
        response = self.app.post('/admin/api/add-question',
                                json=data,
                                content_type='application/json',
                                headers=headers)
        self.assertEqual(response.status_code, 400)
        
        # Test invalid answer index
        data = {"question": "Test?", "options": ["A", "B"], "answer": 5}
        response = self.app.post('/admin/api/add-question',
                                json=data,
                                content_type='application/json',
                                headers=headers)
        self.assertEqual(response.status_code, 400)
    
    def test_admin_export_leaderboard(self):
        """Test CSV export functionality"""
        headers = self.get_basic_auth_headers()
        response = self.app.get('/admin/api/export-leaderboard', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/csv; charset=utf-8')
        
        # Check CSV content
        csv_content = response.data.decode('utf-8')
        self.assertIn('rank,name,regno,correct,points,avg_time', csv_content)
        self.assertIn('Test User', csv_content)
        self.assertIn('TEST001', csv_content)
    
    def test_admin_without_credentials_configured(self):
        """Test admin access when credentials not configured"""
        with patch.dict(os.environ, {'ADMIN_USERNAME': '', 'ADMIN_PASSWORD': ''}):
            # Reload the app module to pick up new env vars
            import importlib
            import app as app_module
            importlib.reload(app_module)
            
            test_app = app_module.app.test_client()
            headers = self.get_basic_auth_headers()
            response = test_app.get('/admin', headers=headers)
            self.assertEqual(response.status_code, 500)


class QuizLogicTestCase(unittest.TestCase):
    """Test quiz scoring logic"""
    
    def setUp(self):
        os.environ['DB_URL'] = 'sqlite:///:memory:'
        from models import db, Participant, Result
        db.drop_tables([Answer, Result, Participant], safe=True)
        db.create_tables([Participant, Result, Answer], safe=True)
        
        self.participant = Participant.create(
            name="Logic Test",
            regno="LOGIC001",
            college="Test",
            dept="CS",
            year=2023
        )
    
    def tearDown(self):
        from models import db, Answer, Result, Participant
        db.drop_tables([Answer, Result, Participant], safe=True)
    
    def test_scoring_logic(self):
        """Test that scoring works correctly"""
        # Create test questions
        test_questions = [
            {"question": "Q1", "options": ["A", "B"], "answer": 0},
            {"question": "Q2", "options": ["A", "B"], "answer": 1},
        ]
        
        with patch('builtins.open', unittest.mock.mock_open(read_data=json.dumps(test_questions))):
            # Test with all correct answers
            answers = [
                {"qId": 0, "selected": 0, "time_sec": 10},  # Correct
                {"qId": 1, "selected": 1, "time_sec": 15},  # Correct
            ]
            
            app_instance = app.test_client()
            response = app_instance.post('/submit-quiz', json={
                "name": "Logic Test",
                "regno": "LOGIC001",
                "answers": answers
            })
            
            self.assertEqual(response.status_code, 200)
            result = Result.get(Result.participant == self.participant)
            self.assertEqual(result.correct, 2)
            self.assertEqual(result.points, 4)  # 2 points each
            self.assertEqual(result.avg_time, 12.5)  # (10+15)/2


if __name__ == '__main__':
    # Run with verbose output
    unittest.main(verbosity=2)
