docker build -t my-rag-lambda . 
docker tag my-rag-lambda:latest XXXXXXXXX.dkr.ecr.us-east-1.amazonaws.com/my-rag-lambda:latest
docker push XXXXXXXXXX.dkr.ecr.us-east-1.amazonaws.com/my-rag-lambda:latest
aws lambda update-function-code --function-name test-rag-container --image-uri XXXXXXXXX.dkr.ecr.us-east-1.amazonaws.com/my-rag-lambda:latest &> /dev/null

