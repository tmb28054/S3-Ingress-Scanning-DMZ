#!/bin/bash -xe

export PREFIX=`date +%Y-%m-%d-%H-%M-%S`

aws ecr-public get-login-password \
  | docker login --username AWS --password-stdin  public.ecr.aws

docker build \
  --no-cache \
  -t ${DOCKER_REPO}:${PREFIX} \
  -f Dockerfile .

aws ecr get-login-password --region ${AWS_REGION} \
  | docker login --username AWS --password-stdin ${CodeBuildLogin}

docker push ${DOCKER_REPO}:${PREFIX}

printf '{"ImageTag": "%s"}' "${PREFIX}" > parameters.json
