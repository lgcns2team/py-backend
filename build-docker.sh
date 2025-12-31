#!/bin/bash
# Build script for Mac M1 users to target ECS (linux/amd64)

IMAGE_NAME="aibackend"
PLATFORM="linux/amd64"

echo "Building Docker image for $PLATFORM..."

# Ensure buildx is used
docker buildx build --platform $PLATFORM -t $IMAGE_NAME:latest . --load

echo "Build complete. You can now tag and push this to ECR."
# Example:
# docker tag aibackend:latest <aws_account_id>.dkr.ecr.<region>.amazonaws.com/aibackend:latest
# docker push <aws_account_id>.dkr.ecr.<region>.amazonaws.com/aibackend:latest
