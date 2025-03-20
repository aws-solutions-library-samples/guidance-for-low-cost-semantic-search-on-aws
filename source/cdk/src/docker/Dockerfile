# Use the AWS base image for Python 3.12
FROM --platform=linux/amd64 public.ecr.aws/lambda/python:3.12

# Install build-essential to get the C++ compiler and other necessary tools
RUN microdnf update -y && microdnf install -y gcc-c++ make

# Copy requirements.txt
COPY requirements.txt ${LAMBDA_TASK_ROOT}

# Install the specified packages
RUN pip install -r requirements.txt

# Copy function code
COPY dynamodb_retriever.py ${LAMBDA_TASK_ROOT}

# Copy function code
COPY utils.py ${LAMBDA_TASK_ROOT}

# Copy function code
COPY bedrock_lambda_function.py ${LAMBDA_TASK_ROOT}

# Set the permissions to make the file executable
RUN chmod +x bedrock_lambda_function.py

# Copy qnaUtils
COPY qnaUtils.py ${LAMBDA_TASK_ROOT}

USER 1001
HEALTHCHECK --interval=5s CMD echo "hello_lambda"
# Set the CMD to your handler
CMD [ "bedrock_lambda_function.lambda_handler" ]