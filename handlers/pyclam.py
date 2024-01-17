#!/usr/bin/env python
"""
    Description
    I run clamav on files and store the result.

    Scenarios
        A scan job has been put in the queue:
            - I scan the file, record results
"""


import json
import logging
import os
import subprocess  # nosec:blacklist:we are using subprocess


import boto3


logger = logging.getLogger()
logger.addHandler(logging.StreamHandler()) # Writes to console
logger.setLevel(logging.INFO)
logging.getLogger('boto3').setLevel(logging.CRITICAL)
logging.getLogger('botocore').setLevel(logging.CRITICAL)
logging.getLogger('s3transfer').setLevel(logging.CRITICAL)
logging.getLogger('urllib3').setLevel(logging.CRITICAL)


LOG = logging.getLogger()
Q_BUCKET = os.getenv('Q_BUCKET')
DMZ_BUCKET = os.getenv('DMZ_BUCKET')
S3 = boto3.client('s3')
SNS = boto3.client('sns')


def notify(data: dict) -> None:
    """I notify the sns topic with the scan results

    Args:
        data (dict): The scan results
    """
    message = {
        'default': json.dumps(data),
        'email': \
            f"""
            Scan Results of {data['filename']}
            Status: {data['status']}
            Bucket: {data['bucket']}
            Output:
            {data['output']}
            """,
        'sms': json.dumps(
            {
                'filename': data['filename'],
                'status': data['status'],
            },
            indent=2
        )
    }
    attributes = {
        'status': {
            'DataType': 'String',
            'StringValue': str(data['status'])
        },
        'filename': {
            'DataType': 'String',
            'StringValue': str(data['filename'])
        },
    }
    LOG.debug(json.dumps(attributes, indent=2))
    response = SNS.publish(
        TopicArn=os.getenv('TOPIC'),
        Subject=data['filename'],
        MessageStructure='json',
        Message=json.dumps(message),
        MessageAttributes=attributes
    )
    LOG.debug(json.dumps(response, default=str))


def _move(src_bucket: str, dst_bucket: str, key: str) -> None:
    """Move from object form one bucket to another

    Args:
        src_bucket (str): the bucket to move object from
        dest_bucket (str): the bucket to move the object to
        key (str): the key for the object to move
    """
    LOG.info('moving s3://%s/%s to s3://%s/%s', src_bucket, key, dst_bucket, key)
    copy_source = {'Bucket': src_bucket, 'Key': key}
    response = S3.copy_object(
        CopySource=copy_source,
        Bucket=dst_bucket,
        Key=key
    )
    LOG.debug(json.dumps(response, default=str))

    response = S3.delete_object(
        Bucket=src_bucket,
        Key=key

    )
    LOG.debug(json.dumps(response, default=str))


def _work_job(bucket, key) -> None:
    """
        I work the job and save the output to s3.  Then update the dynamodb.

        Args:
            bucket: the bucket which has the object
            key: the object to scan

        Returns:
        None
    """
    file_name = os.path.basename(key)
    scratch_file =  f'/tmp/{file_name}'  # nosec: tmp is the lambda disk
    S3.download_file(bucket, key, scratch_file)

    command = [
            '/usr/bin/clamscan',
            '--tempdir=/tmp',
            '--stdout',
            '--archive-verbose',
            str(scratch_file)
    ]

    LOG.info(' '.join(command))
    result = subprocess.run(  # nosec: no shell in lambba
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )

    output = result.stdout.decode("utf-8").replace('/tmp/', '')
    LOG.info('Output is %s', output)

    state = 'failed'
    dst_bucket = Q_BUCKET
    if result.returncode in [0]:
        state = 'pass'
        dst_bucket = DMZ_BUCKET

    # Clean local file
    os.remove(scratch_file)
    notify(
        {
            'bucket': bucket,
            'key': key,
            'status': state,
            'output': output,
            'filename': file_name
        }
    )

    _move(bucket, dst_bucket, key)


def handler(event, _) -> dict:
    """
        I am the logic manager for evaluation job CRUD.

        Args
        event: the context of the api call.

        returns:
        dict: a dictionary of the job context.
    """
    LOG.debug(json.dumps(event, default=str))
    for record in event['Records']:
        body = json.loads(record['body'])
        LOG.debug(json.dumps(body, default=str))
        for s3_record in body['Records']:
            bucket = s3_record['s3']['bucket']['name']
            key = s3_record['s3']['object']['key']
            _work_job(bucket, key)


if __name__ == '__main__':
    with open('example.json', encoding='utf8') as file_buffer:
        example = json.loads(
            file_buffer.read()
        )

    handler(example, {})
