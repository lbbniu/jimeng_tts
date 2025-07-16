import os
import logging
import azure.cognitiveservices.speech as speechsdk
from .submaker import SubMaker, TTSChunk

logger = logging.getLogger(__name__)

class AudioProcessor:
    """音频处理器 - 负责文本转语音和字幕生成"""
    
    def __init__(self):
        """初始化音频处理器"""
        self._validate_azure_config()
    
    def _validate_azure_config(self) -> bool:
        """验证Azure语音服务配置"""
        speech_key = os.environ.get('SPEECH_KEY')
        endpoint = os.environ.get('ENDPOINT')
        
        if not speech_key or not endpoint:
            logger.error("[AudioProcessor] 缺少Azure语音服务配置")
            logger.error("[AudioProcessor] 请设置环境变量: SPEECH_KEY 和 ENDPOINT")
            return False
        
        logger.debug("[AudioProcessor] Azure语音服务配置验证通过")
        return True
    
    def text_to_speech(self, filename: str, text: str, 
                      voice_name: str = 'zh-CN-YunzeNeural',
                      generate_srt: bool = True,
                      merge_words: int = 10) -> bool:
        """文本转语音并生成字幕文件
        
        Args:
            filename: 输出文件名（不含扩展名）
            text: 要转换的文本
            voice_name: 语音名称，默认为中文云泽神经语音
            generate_srt: 是否生成SRT字幕文件
            merge_words: 字幕合并词数，用于优化剪映导入
            
        Returns:
            bool: 是否成功生成音频和字幕
        """
        try:
            # 验证配置
            if not self._validate_azure_config():
                return False
            
            # 验证输入参数
            if not text or not text.strip():
                logger.error("[AudioProcessor] 文本内容不能为空")
                return False
            
            if not filename:
                logger.error("[AudioProcessor] 文件名不能为空")
                return False
            
            # 创建语音配置
            speech_config = speechsdk.SpeechConfig(
                subscription=os.environ.get('SPEECH_KEY'), 
                endpoint=os.environ.get('ENDPOINT')
            )
            
            # 设置音频输出格式为高质量MP3
            speech_config.set_speech_synthesis_output_format(
                speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
            )
            
            # 设置语音名称
            speech_config.speech_synthesis_voice_name = voice_name
            
            # 创建音频输出配置
            audio_config = speechsdk.audio.AudioOutputConfig(filename=filename)
            
            # 创建字幕生成器
            submaker = SubMaker()
            
            # 定义词边界回调函数
            def speech_synthesizer_word_boundary_cb(evt: speechsdk.SpeechSynthesisWordBoundaryEventArgs):
                """处理词边界事件，用于生成字幕"""
                # 将duration转换为100纳秒单位（与offset保持一致）
                duration_in_100ns = int(evt.duration.total_seconds() * 10000000)
                
                submaker.feed(TTSChunk(
                    type="WordBoundary",
                    offset=evt.audio_offset,
                    duration=duration_in_100ns,
                    text=evt.text
                ))
                
                logger.debug(f"[AudioProcessor] 词边界事件: {evt.text}")
            
            # 创建语音合成器
            speech_synthesizer = speechsdk.SpeechSynthesizer(
                speech_config=speech_config, 
                audio_config=audio_config
            )
            
            # 连接词边界事件
            speech_synthesizer.synthesis_word_boundary.connect(speech_synthesizer_word_boundary_cb)
            
            # 执行语音合成
            logger.info(f"[AudioProcessor] 开始合成语音: {text[:50]}...")
            speech_synthesis_result = speech_synthesizer.speak_text_async(text).get()
            reason = speech_synthesis_result.reason # type: ignore
            
            # 处理合成结果
            if reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
                logger.info(f"[AudioProcessor] 语音合成成功: {filename}")
                
                # 生成字幕文件
                if generate_srt:
                    success = self._generate_srt_file(submaker, filename, merge_words)
                    if not success:
                        logger.warning("[AudioProcessor] 字幕文件生成失败")
                
                return True
                
            elif reason == speechsdk.ResultReason.Canceled:
                cancellation_details = speech_synthesis_result.cancellation_details # type: ignore
                logger.error(f"[AudioProcessor] 语音合成被取消: {cancellation_details.reason}")
                
                if cancellation_details.reason == speechsdk.CancellationReason.Error:
                    if cancellation_details.error_details:
                        logger.error(f"[AudioProcessor] 错误详情: {cancellation_details.error_details}")
                    logger.error("[AudioProcessor] 请检查Azure语音服务配置")
                
                return False
            else:
                logger.error(f"[AudioProcessor] 语音合成失败，原因: {reason}")
                return False
                
        except Exception as e:
            logger.error(f"[AudioProcessor] 语音合成异常: {e}")
            return False
    
    def _generate_srt_file(self, submaker: SubMaker, filename: str, merge_words: int) -> bool:
        """生成SRT字幕文件
        
        Args:
            submaker: 字幕生成器
            filename: 文件名（不含扩展名）
            merge_words: 合并词数
            
        Returns:
            bool: 是否成功生成字幕文件
        """
        try:
            # 优化字幕：合并短字幕，避免剪映导入问题
            if merge_words > 0:
                submaker.merge_cues(merge_words)
            
            # 生成SRT文件, 扩展名改为srt
            srt_filename = filename.replace(".mp3", ".srt")
            with open(srt_filename, "w", encoding='utf-8') as f:
                srt_content = submaker.get_srt()
                f.write(srt_content)
            
            logger.info(f"[AudioProcessor] 字幕文件已生成: {srt_filename}")
            return True
            
        except Exception as e:
            logger.error(f"[AudioProcessor] 生成字幕文件失败: {e}")
            return False