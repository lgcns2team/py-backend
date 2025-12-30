import sys
from dataclasses import dataclass, field

# ==========================================
# 0. 파이썬 3.11 fairseq 에러 패치 (가장 먼저!)
# ==========================================
# rvc_python을 임포트하기 "전에" 이 코드가 실행되어야 합니다.
try:
    import fairseq.dataclass.configs
    from fairseq.dataclass.configs import (
        CommonConfig, CommonEvalConfig, DistributedTrainingConfig, 
        DatasetConfig, OptimizationConfig, CheckpointConfig,
        BMUFConfig, GenerationConfig, EvalLMConfig, InteractiveConfig
    )
    
    @dataclass
    class PatchedFairseqConfig:
        common: CommonConfig = field(default_factory=CommonConfig)
        common_eval: CommonEvalConfig = field(default_factory=CommonEvalConfig)
        distributed_training: DistributedTrainingConfig = field(default_factory=DistributedTrainingConfig)
        dataset: DatasetConfig = field(default_factory=DatasetConfig)
        optimization: OptimizationConfig = field(default_factory=OptimizationConfig)
        checkpoint: CheckpointConfig = field(default_factory=CheckpointConfig)
        bmuf: BMUFConfig = field(default_factory=BMUFConfig)
        generation: GenerationConfig = field(default_factory=GenerationConfig)
        eval_lm: EvalLMConfig = field(default_factory=EvalLMConfig)
        interactive: InteractiveConfig = field(default_factory=InteractiveConfig)
        model: Any = None
        task: Any = None

    # 원본 클래스를 우리가 만든 패치 클래스로 교체
    fairseq.dataclass.configs.FairseqConfig = PatchedFairseqConfig
    print("[성공] Python 3.11용 fairseq 패치가 적용되었습니다.")
except Exception as e:
    print(f"[정보] 패치 적용 중 참고: {e}")

# ==========================================
# 1. 나머지 라이브러리 임포트
# ==========================================
import asyncio
import os
import uuid
import argparse
from rvc_python.infer import RVCInference # 패치 후에 임포트!
import edge_tts
import torch

# ==========================================
# 2. RVC 변환 로직
# ==========================================
def run_rvc_conversion(input_audio_path, model_path, index_path, output_path, pitch):
    print(f"[-] RVC 변환 시작 (Pitch: {pitch})")
    
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"모델 파일 없음: {model_path}")

    # GPU 체크
    device = "cuda" if torch.cuda.is_available() else "cpu"
    rvc = RVCInference(device=device)
    
    # 모델 로드
    rvc.load_model(model_path, version="v2", index_path=index_path or "")
    rvc.set_params(f0up_key=pitch, f0method="rmvpe", index_rate=0.75)
    
    # 변환 실행
    rvc.infer_file(input_audio_path, output_path)
    print(f"[완료] 카리나 목소리 생성됨: {output_path}")

# ==========================================
# 3. 메인 실행부
# ==========================================
async def text_to_speech(text, output_path):
    communicate = edge_tts.Communicate(text, "ko-KR-SunHiNeural")
    await communicate.save(output_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, required=True)
    parser.add_argument("--model", type=str, required=True)
    parser.add_argument("--index", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--f0_up_key", type=int, default=12)
    args = parser.parse_args()

    temp_wav = f"temp_{uuid.uuid4().hex}.wav"
    
    try:
        # 입력이 텍스트면 음성으로 먼저 변환
        if not args.input.lower().endswith(".wav"):
            asyncio.run(text_to_speech(args.input, temp_wav))
            input_source = temp_wav
        else:
            input_source = args.input

        # RVC 변환 실행
        run_rvc_conversion(input_source, args.model, args.index, args.output, args.f0_up_key)

    except Exception as e:
        print(f"[에러] {e}")
        sys.exit(1)
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)