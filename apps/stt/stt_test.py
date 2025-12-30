import whisper

# POC 권장 모델
model = whisper.load_model("base")

result = model.transcribe(
    "sample2.wav",
    language="ko"
)

print("=== STT RESULT ===")
print(result["text"])
