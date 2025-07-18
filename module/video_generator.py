"""
视频生成模块 - 使用 pyJianYingDraft 生成剪映草稿
"""

import os
import time
import uuid
import random
import json
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Any
import sys
import shutil

# 添加本地 pyJianYingDraft 模块路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pyJianYingDraft'))

import pyJianYingDraft as draft
from pyJianYingDraft import trange
from pyJianYingDraft.metadata import FontType
from pyJianYingDraft.local_materials import VideoMaterial, AudioMaterial
from pyJianYingDraft.metadata import VideoSceneEffectType

logger = logging.getLogger(__name__)


class VideoGenerator:
    """视频生成器 - 使用 pyJianYingDraft 生成剪映草稿"""
    
    def __init__(self, output_dir: str | None = None):
        """
        初始化视频生成器
        
        Args:
            output_dir: 输出目录，默认为剪映草稿目录
        """
        if output_dir is None:
            # 默认使用剪映草稿目录
            self.output_dir = Path("/Users/lbbniu/Movies/JianyingPro/5.9.0/JianyingPro Drafts")
        else:
            self.output_dir = Path(output_dir)
        
        self.output_dir.mkdir(exist_ok=True)
        logger.info(f"视频生成器初始化完成，输出目录: {self.output_dir}")
    
    def get_file_creation_time(self, file_path: str) -> int:
        """
        获取文件的创建时间（微秒时间戳）
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件创建时间的微秒时间戳
        """
        try:
            # 获取文件状态信息
            stat = os.stat(file_path)
            
            # 在macOS上，st_birthtime是创建时间
            # 在Linux上，st_ctime是创建时间
            # 在Windows上，st_ctime是创建时间
            if hasattr(stat, 'st_birthtime'):
                # macOS
                creation_time = stat.st_birthtime
            else:
                # Linux/Windows，使用修改时间作为创建时间
                creation_time = stat.st_mtime
            
            # 转换为微秒时间戳
            creation_time_us = int(creation_time * 1e6)
            
            logger.debug(f"文件 {file_path} 创建时间: {creation_time_us} 微秒")
            return int(creation_time_us / 1e6)
            
        except Exception as e:
            logger.warning(f"获取文件 {file_path} 创建时间失败: {e}")
            # 如果获取失败，返回当前时间
            return int(time.time())
    
    def get_audio_duration(self, audio_file: str) -> float:
        """
        获取音频文件的时长（秒）
        
        Args:
            audio_file: 音频文件路径
            
        Returns:
            音频时长（秒）
        """
        try:
            import pymediainfo
            media_info = pymediainfo.MediaInfo.parse(audio_file)
            for track in media_info.tracks:
                if track.track_type == 'Audio':
                    duration_ms = track.duration
                    if duration_ms:
                        return duration_ms / 1000.0
            
            # 备用方法：使用 ffprobe（如果安装了ffmpeg）
            import subprocess
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-show_entries', 
                'format=duration', '-of', 'csv=p=0', audio_file
            ], capture_output=True, text=True)
            if result.returncode == 0:
                return float(result.stdout.strip())
                
        except Exception as e:
            logger.warning(f"无法获取音频时长 {audio_file}: {e}")
            
        return 0.0
    
    def get_scene_files(self, scene_dir: str) -> Dict[str, List[str]]:
        """
        获取场景文件列表
        
        Args:
            scene_dir: 场景目录路径
            
        Returns:
            场景文件字典 {场景名: [图片文件列表]}
        """
        scene_files = {}
        scene_path = Path(scene_dir)
        
        if not scene_path.exists():
            logger.error(f"场景目录不存在: {scene_dir}")
            return scene_files
        
        # 按场景分组图片文件
        for file_path in scene_path.glob("*.jpeg"):
            filename = file_path.name
            if "_" in filename:
                scene_name = filename.split("_")[0]
                if scene_name not in scene_files:
                    scene_files[scene_name] = []
                scene_files[scene_name].append(str(file_path))
        
        # 按场景名排序
        scene_files = dict(sorted(scene_files.items(), key=lambda x: int(x[0].replace("分镜", ""))))
        
        logger.info(f"找到 {len(scene_files)} 个场景，共 {sum(len(files) for files in scene_files.values())} 张图片")
        return scene_files
    
    def get_audio_subtitle_files(self, scene_dir: str) -> Dict[str, Tuple[str, str]]:
        """
        获取音频和字幕文件
        
        Args:
            scene_dir: 场景目录路径
            
        Returns:
            音频字幕文件字典 {场景名: (音频文件, 字幕文件)}
        """
        audio_subtitle_files = {}
        scene_path = Path(scene_dir)
        
        if not scene_path.exists():
            logger.error(f"场景目录不存在: {scene_dir}")
            return audio_subtitle_files
        
        # 查找音频和字幕文件
        for mp3_file in scene_path.glob("*.mp3"):
            scene_name = mp3_file.stem
            srt_file = scene_path / f"{scene_name}.srt"
            
            if srt_file.exists():
                audio_subtitle_files[scene_name] = (str(mp3_file), str(srt_file))
            else:
                logger.warning(f"未找到对应的字幕文件: {srt_file}")
        
        logger.info(f"找到 {len(audio_subtitle_files)} 个音频字幕对")
        return audio_subtitle_files
    
    def create_video_draft(self, 
                          scene_dir: str, 
                          output_name: str = "video_draft",
                          video_width: int = 1080,
                          video_height: int = 1920,
                          random_seed: int | None = None) -> str:
        """
        创建视频草稿
        
        Args:
            scene_dir: 场景目录路径
            output_name: 输出文件名
            video_width: 视频宽度
            video_height: 视频高度
            random_seed: 随机种子
            
        Returns:
            生成的草稿文件路径
        """
        if random_seed is not None:
            random.seed(random_seed)
        
        # 获取场景文件
        scene_files = self.get_scene_files(scene_dir)
        audio_subtitle_files = self.get_audio_subtitle_files(scene_dir)
        if not scene_files or not audio_subtitle_files:
            logger.error("未找到足够的素材文件")
            return ""
        
        try:
            # 生成草稿文件夹路径
            draft_file = self.output_dir / output_name
            
            # 创建草稿脚本对象
            script = draft.ScriptFile(video_width, video_height)
            # template_path = "/Users/lbbniu/Movies/JianyingPro/02孩子为你自己读书/draft_content.json"
            # script = draft.ScriptFile.load_template(template_path)
            
            # 收集并添加素材到草稿文件夹（在创建草稿之前）
            materials = self._collect_and_add_materials(script, scene_files, audio_subtitle_files, str(draft_file))
            
            # 创建视频、音频、字幕和特效轨道
            video_track_name = "main_video"
            audio_track_name = "main_audio"
            subtitle_track_name = "subtitle_track"  # 字幕轨道
            statement_track_name = "statement_track"  # 声明文字轨道
            effect_track_name = "main_effect"
            script.add_track(draft.TrackType.audio, audio_track_name, relative_index=0)
            script.add_track(draft.TrackType.video, video_track_name, relative_index=1)
            script.add_track(draft.TrackType.text, statement_track_name, relative_index=2)  # 声明文字轨道，层级0
            script.add_track(draft.TrackType.text, subtitle_track_name, relative_index=3, flag=1)  # 字幕轨道，层级1
            script.add_track(draft.TrackType.effect, effect_track_name, relative_index=4)
            
            # 为每个场景创建视频片段
            scene_names = list(scene_files.keys())
            current_time_us = 0  # 使用微秒为单位避免浮点数精度问题
            
            for scene_name in scene_names:
                if scene_name not in audio_subtitle_files:
                    logger.warning(f"场景 {scene_name} 缺少音频或字幕文件，跳过")
                    continue
                
                # 随机选择一张图片
                image_files = scene_files[scene_name]
                selected_image = random.choice(image_files)
                
                # 获取音频和字幕文件
                audio_file, subtitle_file = audio_subtitle_files[scene_name]
                
                # 获取音频时长（秒）
                audio_duration = self.get_audio_duration(audio_file)
                # 转为微秒
                start_us = current_time_us
                duration_us = int(audio_duration * 1_000_000)
                
                logger.info(f"处理场景 {scene_name}: 图片={selected_image}, 音频={audio_file}, 字幕={subtitle_file}, 时长={audio_duration:.2f}秒")
                logger.info(f"时间区间: start={start_us}, duration={duration_us}")
                
                # 添加视频、音频和字幕片段（使用预先创建的素材对象）
                video_material = materials['images'][selected_image]
                audio_material = materials['audios'][audio_file]
                self._add_video_segment(script, scene_name, video_material, video_track_name, start_us, duration_us)
                self._add_audio_segment(script, scene_name, audio_material, audio_track_name, start_us, duration_us)
                self._add_subtitle_segment(script, scene_name, subtitle_file, subtitle_track_name, current_time_us / 1_000_000)
                
                # 严格对齐下一个片段的起点，使用微秒计算避免精度问题
                current_time_us = start_us + duration_us
            
            # 添加底部声明文字，覆盖整个视频时长
            self._add_statement_text(script, statement_track_name, current_time_us / 1_000_000)
            
            # 添加雪花特效，持续全片
            try:
                script.add_effect(
                    VideoSceneEffectType.雪花,
                    trange(0, current_time_us),
                    track_name=effect_track_name,
                    params=[33, 10]  # 速度33，背景动画10
                )
                logger.info("成功为全片添加雪花散落特效，速度=33，背景动画=10")
            except Exception as e:
                logger.error(f"添加雪花特效失败: {e}")
            
            # 保存最终的草稿内容
            self._save_draft(script, str(draft_file))
            
            logger.info(f"视频草稿生成完成: {draft_file}")
            return str(draft_file)
            
        except Exception as e:
            logger.error(f"生成视频草稿失败: {e}")
            return ""
    
    def create_video_draft_from_feijing(self, 
                                       feijing_dir: str,
                                       output_name: str | None = None,
                                       video_width: int = 1080,
                                       video_height: int = 1920,
                                       random_seed: int | None = None) -> str:
        """
        从飞镜生成的素材创建视频草稿
        
        Args:
            feijing_dir: 飞镜素材目录路径
            output_name: 输出文件名（默认使用目录名）
            video_width: 视频宽度
            video_height: 视频高度
            random_seed: 随机种子
            
        Returns:
            生成的草稿文件路径
        """
        if output_name is None:
            output_name = Path(feijing_dir).name
        
        return self.create_video_draft(
            scene_dir=feijing_dir,
            output_name=output_name,
            video_width=video_width,
            video_height=video_height,
            random_seed=random_seed
        )

    def _save_draft(self, script, output_path: str) -> None:
        """保存剪映草稿文件夹"""
        try:
            # 确保输出路径是文件夹，而不是文件
            draft_folder = f"{output_path}"
            draft_name = os.path.basename(output_path)
            # 使用指定的模板草稿
            template_path = "/Users/lbbniu/Movies/JianyingPro/人物故事模板"
            if os.path.exists(template_path):
                print(f"使用指定的草稿模板: {template_path}")
                self._create_draft_from_template(script, template_path, draft_folder, draft_name)
            else:
                # 如果模板不存在，回退到手动创建
                print(f"模板路径不存在: {template_path}")
                print("回退到手动创建草稿文件夹")
                self._create_draft_folder_manually(script, draft_folder, draft_name)
            
            print(f"✅ 成功创建剪映草稿文件夹: {draft_folder}")
            print(f"   文件夹包含 {len(os.listdir(draft_folder))} 个文件")
            
        except Exception as e:
            print(f"❌ 保存草稿失败: {e}")
            raise
    
    def _create_draft_from_template(self, script, template_path: str, draft_folder: str, draft_name: str) -> None:
        """从指定模板创建草稿文件夹"""
        
        # 删除现有的草稿文件夹（如果存在）
        if os.path.exists(draft_folder):
            shutil.rmtree(draft_folder)
        
        # 复制模板文件夹
        shutil.copytree(template_path, draft_folder)
        
        # 更新草稿内容
        draft_content_path = os.path.join(draft_folder, "draft_content.json")
        script.dump(draft_content_path)
        
        # 生成虚拟存储文件
        self._generate_draft_virtual_store(script, draft_folder, draft_name)
        
        # 更新元数据中的草稿名称和路径
        self._update_draft_metadata(draft_folder, draft_name, script)
    
    def _update_draft_metadata(self, draft_folder: str, draft_name: str, script) -> None:
        """更新草稿元数据文件"""
        meta_info_path = os.path.join(draft_folder, "draft_meta_info.json")
        
        if os.path.exists(meta_info_path):
            # 读取现有元数据
            with open(meta_info_path, "r", encoding="utf-8") as f:
                meta_info = json.load(f)
            
            # 更新关键字段
            current_time = int(time.time() * 1e6)
            meta_info.update({
                "draft_cover": "",
                "draft_name": draft_name,
                "draft_fold_path": draft_folder,
                "draft_root_path": os.path.dirname(draft_folder),
                "draft_id": str(uuid.uuid4()),
                "tm_draft_create": current_time,
                "tm_draft_modified": current_time
            })
            
            # 更新素材信息
            self._update_draft_materials_info(meta_info, script, current_time)
            
            # 写回文件
            with open(meta_info_path, "w", encoding="utf-8") as f:
                json.dump(meta_info, f, ensure_ascii=False, separators=(',', ':'))
        else:
            logger.warning(f"元数据文件不存在: {meta_info_path}")
    
    def _create_draft_folder_manually(self, script, draft_folder: str, draft_name: str) -> None:
        """手动创建草稿文件夹结构（当没有模板时使用）"""
        # 创建草稿文件夹（如果存在则删除重建）
        if os.path.exists(draft_folder):
            shutil.rmtree(draft_folder)
        os.makedirs(draft_folder, exist_ok=True)
        
        # 保存主要内容文件
        draft_content_path = os.path.join(draft_folder, "draft_content.json")
        script.dump(draft_content_path)
        
        # 生成虚拟存储文件
        self._generate_draft_virtual_store(script, draft_folder, draft_name)

    def _add_statement_text(self, script, statement_track_name: str, total_duration: float) -> None:
        """
        添加底部声明文字轨道和文字内容
        
        Args:
            script: ScriptFile对象
            total_duration: 视频总时长（秒）
        """
        if total_duration <= 0:
            logger.warning("视频时长无效，跳过添加声明文字")
            return
        
        total_duration_us = int(total_duration * 1_000_000)
        statement_text = "图片AI生成和网络下载 科普视频无不良引导\n非专业新闻仅供参考 请勿过分解读"
        
        try:
            statement_segment = draft.TextSegment(
                statement_text,
                trange(0, total_duration_us),  # 覆盖整个视频时长
                font=FontType.新青年体,  # 宋体
                style=draft.TextStyle(
                    size=9,  # 字号9
                    align=1,  # 居中对齐
                    auto_wrapping=True,  # 自动换行
                    alpha=0.7,  # 透明度70%
                    color=(1.0, 1.0, 1.0),  # 白色 (RGB值: 1.0, 1.0, 1.0)
                    max_line_width=0.95  # 最大行宽占屏幕95%，避免不必要的换行
                ),
                clip_settings=draft.ClipSettings(
                    transform_y=-0.90  # 位置在底部
                )
            )
            script.add_segment(statement_segment, track_name=statement_track_name)
            logger.info(f"成功添加底部声明文字，时长: {total_duration:.2f}秒")
        except Exception as e:
            logger.error(f"添加底部声明文字失败: {e}")
            # 声明文字失败不应该阻止整个流程
            logger.warning("跳过底部声明文字")

    def _add_video_segment(self, script, scene_name: str, video_material: VideoMaterial, 
                          video_track_name: str, start_us: int, duration_us: int) -> None:
        """
        添加视频片段到指定轨道，可选择添加出场放大动画
        
        Args:
            script: ScriptFile对象
            scene_name: 场景名称
            video_material: 视频素材对象
            video_track_name: 视频轨道名称
            start_us: 开始时间（微秒）
            duration_us: 持续时间（微秒）
            use_animation: 是否使用出场动画，默认True
        """
        try:
            video_segment = draft.VideoSegment(
                video_material, 
                trange(start_us, duration_us),
                clip_settings=draft.ClipSettings(
                    scale_x=1.1,  # X轴缩放1.1倍
                    scale_y=1.1   # Y轴缩放1.1倍
                )
            )
            from pyJianYingDraft.metadata import OutroType
            video_segment.add_animation(OutroType.放大, duration=duration_us)
            logger.info(f"成功添加视频片段: {scene_name} (素材ID: {video_material.material_id})，初始缩放110%，包含出场放大动画")
            script.add_segment(video_segment, track_name=video_track_name)
        except Exception as e:
            logger.error(f"添加视频片段失败 {scene_name}: {e}")
            raise

    def _add_audio_segment(self, script, scene_name: str, audio_material: AudioMaterial,
                          audio_track_name: str, start_us: int, duration_us: int) -> None:
        """
        添加音频片段到指定轨道
        
        Args:
            script: ScriptFile对象
            scene_name: 场景名称
            audio_material: 音频素材对象
            audio_track_name: 音频轨道名称
            start_us: 开始时间（微秒）
            duration_us: 持续时间（微秒）
        """
        try:
            audio_segment = draft.AudioSegment(
                audio_material,
                trange(start_us, duration_us),
                source_timerange=trange(0, duration_us)
            )
            script.add_segment(audio_segment, track_name=audio_track_name)
            logger.info(f"成功添加音频片段: {scene_name} (素材ID: {audio_material.material_id})")
        except Exception as e:
            logger.error(f"添加音频片段失败 {scene_name}: {e}")
            raise

    def _add_subtitle_segment(self, script, scene_name: str, subtitle_file: str,
                             subtitle_track_name: str, time_offset: float) -> None:
        """
        添加字幕片段到指定轨道
        
        Args:
            script: ScriptFile对象
            scene_name: 场景名称
            subtitle_file: 字幕文件路径
            subtitle_track_name: 字幕轨道名称
            time_offset: 时间偏移（秒）
        """
        try:
            # 手动解析SRT文件以避免片段重叠问题
            subtitles = self._parse_srt_file(subtitle_file)
            
            if not subtitles:
                logger.warning(f"字幕文件为空或解析失败: {subtitle_file}")
                return
            
            # 为每个字幕条目添加到轨道，使用绝对时间偏移
            for subtitle in subtitles:
                # 直接使用场景开始时间作为基准，忽略SRT文件中的原始时间戳
                # 假设每个场景的字幕应该从场景开始就显示
                relative_start = subtitle['start'] - subtitles[0]['start']  # 相对于第一条字幕的偏移
                duration = subtitle['end'] - subtitle['start']
                
                # 计算在整个视频中的绝对时间位置
                absolute_start_time = time_offset + relative_start
                
                # 转换为微秒
                start_us = int(absolute_start_time * 1_000_000)
                duration_us = int(duration * 1_000_000)
                
                # 记录详细的调试信息
                logger.info(f"字幕 {scene_name}: '{subtitle['text'][:20]}...' "
                           f"原始={subtitle['start']:.2f}-{subtitle['end']:.2f}s, "
                           f"偏移={relative_start:.2f}s, "
                           f"绝对位置={absolute_start_time:.2f}s")
                           
                # 检查时间范围是否合理
                if start_us < 0:
                    logger.warning(f"字幕时间为负数，跳过: {scene_name}")
                    continue
                
                # 创建文本片段
                text_segment = draft.TextSegment(
                    subtitle['text'],
                    trange(start_us, duration_us),
                    font=FontType.新青年体,  # 指定字体
                    style=draft.TextStyle(
                        size=14,  # 字体大小
                        align=1,  # 居中对齐
                        auto_wrapping=True,  # 自动换行
                        color=(1.0, 1.0, 0.0),  # 黄色 (RGB: 255, 255, 0)
                        max_line_width=0.95  # 最大行宽占屏幕95%，避免不必要的换行
                    ),
                    border=draft.TextBorder(
                        alpha=1.0,  # 描边不透明度100%
                        color=(0.0, 0.0, 0.0),  # 黑色描边
                        width=60.0  # 描边宽度
                    ),
                    clip_settings=draft.ClipSettings(
                        transform_y=-0.6  # 位置稍微偏下
                    )
                )
                
                # 添加到轨道
                script.add_segment(text_segment, track_name=subtitle_track_name)
                
            logger.info(f"成功添加字幕片段: {scene_name}，共 {len(subtitles)} 条字幕")
        except Exception as e:
            logger.error(f"添加字幕片段失败 {scene_name}: {e}")
            # 字幕失败不应该阻止整个流程
            logger.warning(f"跳过场景 {scene_name} 的字幕")

    def _parse_srt_file(self, subtitle_file: str) -> List[Dict[str, Any]]:
        """
        解析SRT字幕文件
        
        Args:
            subtitle_file: SRT文件路径
            
        Returns:
            字幕条目列表，每个条目包含start, end, text
        """
        subtitles = []
        
        try:
            with open(subtitle_file, 'r', encoding='utf-8-sig') as f:
                content = f.read().strip()
            
            # 按空行分割字幕块
            blocks = content.split('\n\n')
            
            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    # 第一行是序号，跳过
                    # 第二行是时间戳
                    time_line = lines[1]
                    # 第三行及之后是字幕文本
                    text_lines = lines[2:]
                    
                    # 解析时间戳 "00:00:00,000 --> 00:00:03,000"
                    if ' --> ' in time_line:
                        start_str, end_str = time_line.split(' --> ')
                        start_time = self._parse_timestamp(start_str)
                        end_time = self._parse_timestamp(end_str)
                        text = '\n'.join(text_lines)
                        
                        subtitles.append({
                            'start': start_time,
                            'end': end_time,
                            'text': text
                        })
                        
        except Exception as e:
            logger.error(f"解析SRT文件失败 {subtitle_file}: {e}")
            
        return subtitles
    
    def _parse_timestamp(self, timestamp_str: str) -> float:
        """
        解析SRT时间戳为秒数
        
        Args:
            timestamp_str: 时间戳字符串，格式如 "00:00:03,000"
            
        Returns:
            时间（秒）
        """
        # 格式: HH:MM:SS,mmm
        time_part, ms_part = timestamp_str.split(',')
        hours, minutes, seconds = map(int, time_part.split(':'))
        milliseconds = int(ms_part)
        
        total_seconds = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000.0
        return total_seconds

    def _collect_and_add_materials(self, script, scene_files: Dict[str, List[str]], 
                                  audio_subtitle_files: Dict[str, Tuple[str, str]], 
                                  draft_folder: str) -> Dict[str, Any]:
        """
        收集所有素材文件并添加到草稿素材库
        
        Args:
            script: ScriptFile对象
            scene_files: 场景图片文件字典
            audio_subtitle_files: 音频字幕文件字典
            draft_folder: 草稿文件夹路径
            
        Returns:
            素材对象字典，用于后续创建片段时使用
        """
        materials = {
            'images': {},  # {文件路径: VideoMaterial对象}
            'audios': {}   # {文件路径: AudioMaterial对象}
        }
        
        logger.info("开始收集并添加素材到素材库...")
        
        # 收集所有图片素材（直接使用原始文件路径）
        image_count = 0
        for scene_name, image_files in scene_files.items():
            for image_file in image_files:
                if image_file not in materials['images']:
                    try:
                        # 直接使用原始文件路径创建视频素材对象
                        video_material = draft.VideoMaterial(image_file)
                        script.add_material(video_material)
                        materials['images'][image_file] = video_material
                        image_count += 1
                        logger.debug(f"添加图片素材: {image_file}")
                    except Exception as e:
                        logger.error(f"添加图片素材失败 {image_file}: {e}")
        
        # 收集所有音频素材（直接使用原始文件路径）
        audio_count = 0
        for scene_name, (audio_file, subtitle_file) in audio_subtitle_files.items():
            if audio_file not in materials['audios']:
                try:
                    # 直接使用原始文件路径创建音频素材对象
                    audio_material = draft.AudioMaterial(audio_file)
                    script.add_material(audio_material)
                    materials['audios'][audio_file] = audio_material
                    audio_count += 1
                    logger.debug(f"添加音频素材: {audio_file}")
                except Exception as e:
                    logger.error(f"添加音频素材失败 {audio_file}: {e}")
        
        logger.info(f"素材库添加完成: {image_count} 个图片素材, {audio_count} 个音频素材")
        return materials

    def _update_draft_materials_info(self, meta_info: dict, script, current_time: int) -> None:
        """
        更新草稿元数据中的素材信息
        
        Args:
            meta_info: 元数据字典
            script: ScriptFile对象
            current_time: 当前时间戳（微秒）
        """
        try:
            # 收集所有素材信息
            materials_info = []
            
            # 添加视频素材
            for material in script.materials.videos:
                # 获取文件的实际创建时间
                file_creation_time = self.get_file_creation_time(material.path)
                materials_info.append({
                    "create_time": file_creation_time,
                    "duration": material.duration,
                    "extra_info": material.material_name,
                    "file_Path": material.path,
                    "height": material.height,
                    "id": material.material_id,
                    "import_time": int(current_time/1e6),
                    "import_time_ms": current_time,
                    "item_source": 1,
                    "md5": "",
                    "metetype": "photo" if material.material_type == "photo" else "video",
                    "roughcut_time_range": {"duration": -1, "start": -1},
                    "sub_time_range": {"duration": -1, "start": -1},
                    "type": 0,
                    "width": material.width
                })
            
            # 添加音频素材
            for material in script.materials.audios:
                # 获取文件的实际创建时间
                file_creation_time = self.get_file_creation_time(material.path)
                materials_info.append({
                    "create_time": file_creation_time,
                    "duration": material.duration,
                    "extra_info": material.material_name,
                    "file_Path": material.path,
                    "height": 0,
                    "id": material.material_id,
                    "import_time": int(current_time/1e6),
                    "import_time_ms": current_time,
                    "item_source": 1,
                    "md5": "",
                    "metetype": "music",
                    "roughcut_time_range": {"duration": material.duration, "start": 0},
                    "sub_time_range": {"duration": -1, "start": -1},
                    "type": 0,
                    "width": 0
                })
            
            # 更新元数据中的素材信息
            meta_info["draft_materials"] = [
                {
                    "type": 0,
                    "value": materials_info
                },
                {
                    "type": 1,
                    "value": []
                },
                {
                    "type": 2,
                    "value": []
                },
                {
                    "type": 3,
                    "value": []
                },
                {
                    "type": 6,
                    "value": []
                },
                {
                    "type": 7,
                    "value": []
                },
                {
                    "type": 8,
                    "value": []
                }
            ]
            
            logger.info(f"成功更新素材信息: {len(materials_info)} 个素材")
            
        except Exception as e:
            logger.error(f"更新素材信息失败: {e}")

    def _generate_draft_virtual_store(self, script, draft_folder: str, draft_name: str) -> None:
        """
        生成草稿虚拟存储文件 draft_virtual_store.json
        
        Args:
            script: ScriptFile对象
            draft_folder: 草稿文件夹路径
            draft_name: 草稿名称
        """
        try:
            # 生成草稿ID
            draft_id = str(uuid.uuid4())
            current_time = int(time.time())
            current_time_us = int(time.time() * 1e6)
            
            # 收集所有素材信息
            materials_info = []
            
            # 添加视频素材
            for material in script.materials.videos:
                # 获取文件的实际创建时间
                file_creation_time = self.get_file_creation_time(material.path)
                materials_info.append({
                    "creation_time": file_creation_time,  # 转换为秒
                    "display_name": material.material_name,
                    "filter_type": 0,
                    "id": material.material_id,
                    "import_time": current_time,
                    "import_time_us": current_time_us,
                    "sort_sub_type": 0,
                    "sort_type": 0
                })
            
            # 添加音频素材
            for material in script.materials.audios:
                # 获取文件的实际创建时间
                file_creation_time = self.get_file_creation_time(material.path)
                materials_info.append({
                    "creation_time": file_creation_time,  # 转换为秒
                    "display_name": material.material_name,
                    "filter_type": 0,
                    "id": material.material_id,
                    "import_time": current_time,
                    "import_time_us": current_time_us,
                    "sort_sub_type": 0,
                    "sort_type": 0
                })
            
            # 构建虚拟存储数据结构
            virtual_store_data = {
                "draft_materials": [],
                "draft_virtual_store": [
                    {
                        "type": 0,
                        "value": [
                            {
                                "creation_time": 0,
                                "display_name": "",
                                "filter_type": 0,
                                "id": "",
                                "import_time": 0,
                                "import_time_us": 0,
                                "sort_sub_type": 1,
                                "sort_type": 2
                            },
                            {
                                "creation_time": current_time,
                                "display_name": draft_name,
                                "filter_type": 0,
                                "id": draft_id,
                                "import_time": current_time,
                                "import_time_us": current_time_us,
                                "sort_sub_type": 0,
                                "sort_type": 0
                            }
                        ]
                    },
                    {
                        "type": 1,
                        "value": [
                            {
                                "child_id": draft_id,
                                "parent_id": ""
                            }
                        ] + [
                            {
                                "child_id": material["id"],
                                "parent_id": draft_id
                            }
                            for material in materials_info
                        ]
                    },
                    {
                        "type": 2,
                        "value": []
                    }
                ]
            }
            
            # 保存虚拟存储文件
            virtual_store_path = os.path.join(draft_folder, "draft_virtual_store.json")
            with open(virtual_store_path, "w", encoding="utf-8") as f:
                json.dump(virtual_store_data, f, ensure_ascii=False, separators=(',', ':'))
            
            logger.info(f"成功生成虚拟存储文件: {virtual_store_path}")
            
        except Exception as e:
            logger.error(f"生成虚拟存储文件失败: {e}")


def main():
    """测试函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="生成剪映视频草稿")
    parser.add_argument("--input", "-i", required=True, help="输入素材目录")
    parser.add_argument("--output", "-o", help="输出文件名")
    parser.add_argument("--width", type=int, default=1080, help="视频宽度")
    parser.add_argument("--height", type=int, default=1920, help="视频高度")
    parser.add_argument("--seed", type=int, help="随机种子")
    
    args = parser.parse_args()
    
    generator = VideoGenerator()
    draft_file = generator.create_video_draft_from_feijing(
        feijing_dir=args.input,
        output_name=args.output,
        video_width=args.width,
        video_height=args.height,
        random_seed=args.seed
    )
    
    if draft_file:
        print(f"草稿文件生成成功: {draft_file}")
    else:
        print("草稿文件生成失败")


if __name__ == "__main__":
    main() 