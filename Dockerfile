# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# Use --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code to the working directory
COPY . .

# Make port 8080 available to the world outside this container
# Google Cloud Run expects the container to listen on the port defined by the PORT env var.
# Gunicorn will bind to 0.0.0.0:$PORT by default.
EXPOSE 8080

# Define environment variable
ENV PORT 8080

# Run app.py when the container launches
# Use Gunicorn as the production WSGI server
# --workers 3: A common starting point for the number of worker processes
# --timeout 120: Increase timeout to prevent worker timeouts on longer requests
# app:app: Tells Gunicorn to look for the 'app' object in the 'app.py' file
CMD ["gunicorn", "--workers", "3", "--timeout", "120", "app:app", "--bind", "0.0.0.0:8080"]
