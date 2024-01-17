FROM public.ecr.aws/docker/library/python:3.12

# Copy function code
RUN test -e /function || mkdir -p /function
COPY ./handlers/pyclam.py /function

# Install the function's dependencies
RUN pip install \
    --target /function \
        awslambdaric

RUN pip install boto3

RUN apt update
RUN apt -y upgrade
RUN apt -y install clamav
RUN freshclam

# Set working directory to function root directory
WORKDIR /function

# Set runtime interface client as default command for the container runtime
ENTRYPOINT [ "/usr/local/bin/python", "-m", "awslambdaric" ]
# Pass the name of the function handler as an argument to the runtime
CMD [ "pyclam.handler" ]
