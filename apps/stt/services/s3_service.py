# S3 연동 서비스
import boto3
from django.conf import settings
from botocore.client import Config

class S3Service:
    def __init__(self):
        #  EC2 IAM Role 환경이면 access key 없어도 동작
        self.s3 = boto3.client(
            "s3",
            region_name=getattr(settings, "AWS_REGION", None),
            aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
            aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
            config=Config(signature_version="s3v4"),
        )
        self.bucket = settings.AWS_S3_BUCKET_NAME

    def create_presigned_put_url(self, key: str, content_type: str, expires_in: int = 300) -> str:
        """
        프론트가 S3로 직접 업로드하게 하는 presigned PUT URL 생성
        """
        return self.s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )

    def head_object(self, key: str) -> dict:
        """
        업로드가 실제로 되었는지 확인 (메타데이터 조회)
        """
        return self.s3.head_object(Bucket=self.bucket, Key=key)

    def download_to_file(self, key: str, local_path: str) -> None:
        """
        S3 객체를 로컬 파일로 다운로드
        """
        self.s3.download_file(self.bucket, key, local_path)
