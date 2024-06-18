import os
import boto3
import json
import base64
import configparser
import argparse
import sys
import secrets
import yaml
import docker
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Random import get_random_bytes
from datetime import date

# Initialize Docker client
client = docker.from_env()

# Read in variables from docker-compose.yml
with open('environment.yaml') as f:
    env_variables_file = yaml.safe_load(f)

queue_url = env_variables_file["variables"]["queueUrl"]
localstack_container_name = env_variables_file["variables"]["localstackContainer"]
localstack_port = env_variables_file["variables"]["localstackPort"]
postgres_container_name = env_variables_file["variables"]["postgresContainer"]
postgres_port = env_variables_file["variables"]["postgresPort"]
postgres_host = env_variables_file["variables"]["postgresHost"]
postgres_password = env_variables_file["variables"]["postgresPassword"]
aes_key_path = env_variables_file["variables"]["aesKeyPath"]

# read in generated key for AES encryption
# Typically, the key can be generated and stores using a key management system
# Need to ensure that the key is securely stored
with open(aes_key_path, 'rb') as f:
    key = f.read()
print(f"Key read from file: {key}")


# Parse the SQS message and convert into a python dictionary for easy access
def parse_sqs_messages(sqs_message):
    try:
        # Loads the message and body portion of the SQS message into a python dictionary
        message_dict = json.loads(sqs_message)
        message_dict["Messages"][0]["Body"] = json.loads(message_dict["Messages"][0]["Body"])
        return message_dict

    except (KeyError, IndexError, json.JSONDecodeError) as e:
        print(f"Error parsing SQS message: {e}")
        return str(e)

# Decided to use AES encryption for maksing PII because it needs to be highly protected
# Additonally, with this implementation, encryption is deterministic, meaning that encrypting plaintext
# using the same key withh produce the same ciphertext every time.
# AES encryption is also reversible and can be decrypted with the key
def AES_encrypt(string_to_encrypt):
    try:
        # create cipher in CBC mode
        cipher = AES.new(key, AES.MODE_CBC)
        padded_plaintext = pad(string_to_encrypt.encode('utf-8'), AES.block_size)
        # encrypt padded plaintext
        ciphertext = cipher.encrypt(padded_plaintext)
        iv = base64.b64encode(cipher.iv).decode('utf-8')
        encrypted_text = base64.b64encode(ciphertext).decode('utf-8')
        # Use initialization vector and encrypted text to create the entire encrypted message
        return iv + encrypted_text
    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return str(e)

# Writes relevant information to the postgres database
def write_to_postgres(sqs_message_dict):
    sqs_message = sqs_message_dict['Messages'][0]
    sqs_message_body = sqs_message['Body']
    try:
        # Extract values to insert to postgres from JSON dictionary
        user_id = sqs_message_body['user_id']
        device_type = sqs_message_body['device_type']
        masked_ip = sqs_message_body['ip']
        masked_device_id = sqs_message_body['device_id']
        locale = sqs_message_body['locale']
        app_version = int(sqs_message_body['app_version'].replace('.', ''))
        create_date = date.today().isoformat()
    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return str(e)
    try:
        # Construct the insert message command
        insert_message_command = f"INSERT INTO user_logins (user_id, device_type, masked_ip, masked_device_id, locale, app_version, create_date) VALUES ('{user_id}', '{device_type}', '{masked_ip}', '{masked_device_id}', '{locale}', {app_version}, '{create_date}');"

        print(f"Executing SQL command: {insert_message_command}")

        # Define the psql command for execution
        psql_command = [
            'psql',
            '-d', postgres_host,
            '-U', postgres_host,
            '-p', postgres_port,
            '-h', 'localhost',
            '-c', insert_message_command
        ]

        container = client.containers.get(postgres_container_name)
        # creates the Docker exec statement that runs the SQL command to insert message into user_logins table
        exec_id = client.api.exec_create(container.id, psql_command, stdout=True, stderr=True, environment=postgres_password)

        output = client.api.exec_start(exec_id['Id'], stream=True)

        for line in output:
            print(line.decode('utf-8').strip())

        print("Insertion completed.")

    except docker.errors.NotFound:
        print(f"Container {postgres_container_name} not found")
        return f"Container {postgres_container_name} not found"
    except docker.errors.APIError as e:
        print(f"Docker API error: {str(e)}")
        return str(e)
    except Exception as e:
        print(f"Exception occurred: {str(e)}")
        return str(e)

def process_sqs_messages(localstack_container_name):
    try:
        
        container = client.containers.get(localstack_container_name)
        receive_message_command = f'awslocal sqs receive-message --queue-url {queue_url}'

        # Start of the process that receives SQS messages from the queue and writes to Postgres database
        # Continues to receive messages until queue is empty
        while True:
            # Creates Docker exec command to receive message
            exec_id = client.api.exec_create(container.id, receive_message_command)
            sqs_message = client.api.exec_start(exec_id)

            # Exits function if no message or empty message is received
            if not sqs_message or sqs_message.strip() == '':
                print("Empty message received. Exiting the function.")
                break

            # Calls function to parse sqs message into a python dictionary for easy access
            parsed_sqs_message = parse_sqs_messages(sqs_message)

            # Checks to see if the message is missing ip or device_id
            # if both are present, it encrypts them, else it skips to the next message
            try:
                if 'ip' and 'device_id' in parsed_sqs_message['Messages'][0]['Body']:
                    parsed_sqs_message['Messages'][0]['Body']['ip'] = AES_encrypt(parsed_sqs_message['Messages'][0]['Body']['ip'])
                    parsed_sqs_message['Messages'][0]['Body']['device_id'] = AES_encrypt(parsed_sqs_message['Messages'][0]['Body']['device_id'])
            except (KeyError, IndexError):
                print("Skipping message: 'ip', 'device_id' or message structure issue")
                continue 

            print(parsed_sqs_message)
            # Writes the relevent attributes to postgres
            write_to_postgres(parsed_sqs_message)
            
    except docker.errors.NotFound:
        print(f"Container {localstack_container_name} not found")
        return f"Container {localstack_container_name} not found", None
    except docker.errors.APIError as e:
        print(f"Exception occurred: {str(e)}")
        return str(e), None   
    except Exception as e:
        print(f"Exception occurred 1: {str(e)}")
        return str(e) 

process_sqs_messages(localstack_container_name)


