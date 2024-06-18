
# SQS ETL application

This repository contains an ETL (Extract, Transform, Load) application that reads messages from an SQS queue and writes them into a PostgreSQL database.

## Prerequisites
Before running this application, make sure you have the following installed:

- Docker
- Docker Compose
- PostgreSQL

## Getting Started
1. **Clone the repository:**
```bash
   git clone https://github.com/your-username/sqs-etl-application.git
   cd sqs-etl-application
```
2. **Set up Docker containers**
Use Docker to simulate AWS services locally. Run the following command to start Docker containers for LocalStack (for SQS emulation) and PostgreSQL:
```bash
   docker-compose up
```
3. **Create a virtual environment**
To create a Conda environment with the required dependencies:
```
conda env create -f environment.yml
conda activate etl-env
```
4. **Run the ETL script**
Now, you can run the ETL script to start extracting messages from the SQS queue and loading them into the PostgreSQL database:
```
python etl.py
```
The script will continuously read messages from the SQS queue and insert them into the PostgreSQL database. Use Ctrl + C to terminate the program.

## Notes
 - Configuration: Modify config.py to adjust SQS queue settings, database credentials, or other configuration options.
 - Logging: Check logs for detailed information on data processing and any errors encountered.

 ##Cleanup
 After you finish using the application, you can stop and remove Docker containers:
 ```
 docker-compose down
 ```