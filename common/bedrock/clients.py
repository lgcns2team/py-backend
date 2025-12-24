import boto3
from django.conf import settings

class BedrockClients:
    """Bedrock 클라이언트 싱글톤"""
    _runtime = None
    _agent_runtime = None
    _agent = None
    
    @classmethod
    def get_runtime(cls):
        if cls._runtime is None:
            cls._runtime = boto3.client(
                service_name='bedrock-runtime',
                region_name=settings.AWS_REGION
            )
        return cls._runtime
    
    @classmethod
    def get_agent_runtime(cls):
        if cls._agent_runtime is None:
            cls._agent_runtime = boto3.client(
                service_name='bedrock-agent-runtime',
                region_name=settings.AWS_REGION
            )
        return cls._agent_runtime
    
    @classmethod
    def get_agent(cls):
        if cls._agent is None:
            cls._agent = boto3.client(
                service_name='bedrock-agent',
                region_name=settings.AWS_REGION
            )
        return cls._agent