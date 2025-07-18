"""SubMaker module is used to generate subtitles from WordBoundary events."""

from typing import List

import srt  # type: ignore

from typing_extensions import Literal, NotRequired, TypedDict

class TTSChunk(TypedDict):
    """TTS chunk data."""

    type: Literal["audio", "WordBoundary"]
    data: NotRequired[bytes]  # only for audio
    duration: NotRequired[float]  # only for WordBoundary
    offset: NotRequired[float]  # only for WordBoundary
    text: NotRequired[str]  # only for WordBoundary

class SubMaker:
    """
    SubMaker is used to generate subtitles from WordBoundary messages.
    """

    def __init__(self) -> None:
        self.cues: List[srt.Subtitle] = []  # type: ignore

    def feed(self, msg: TTSChunk) -> None:
        """
        Feed a WordBoundary message to the SubMaker object.

        Args:
            msg (dict): The WordBoundary message.

        Returns:
            None
        """
        if msg["type"] != "WordBoundary":
            raise ValueError("Invalid message type, expected 'WordBoundary'")

        self.cues.append(
            srt.Subtitle(
                index=len(self.cues) + 1,
                start=srt.timedelta(microseconds=msg["offset"] / 10), # type: ignore
                end=srt.timedelta(microseconds=(msg["offset"] + msg["duration"]) / 10), # type: ignore
                content=msg["text"] # type: ignore
            )
        )

    def merge_cues(self, words: int) -> None:
        """
        Merge cues to reduce the number of cues.

        Args:
            words (int): The number of words to merge.

        Returns:
            None
        """
        if words <= 0:
            raise ValueError("Invalid number of words to merge, expected > 0")

        if len(self.cues) == 0:
            return

        new_cues: List[srt.Subtitle] = []
        current_cue: srt.Subtitle = self.cues[0]
        
        def count_words(text: str) -> int:
            """Count words in text, handling both Chinese and English text."""
            # 对于中文字符，每个字符算作一个单位
            # 对于英文，按空格分割计算单词数
            chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
            english_words = len([word for word in text.split() if any(c.isalpha() for c in word)])
            return chinese_chars + english_words
        
        for cue in self.cues[1:]:
            current_word_count = count_words(current_cue.content)
            cue_word_count = count_words(cue.content)
            if current_word_count + cue_word_count <= words:
                current_cue = srt.Subtitle(
                    index=current_cue.index,
                    start=current_cue.start,
                    end=cue.end,
                    content=current_cue.content + cue.content,
                )
            else:
                new_cues.append(current_cue)
                current_cue = cue
        
        new_cues.append(current_cue)
        
        # 重新编号索引以保持连续性
        for i, cue in enumerate(new_cues):
            cue.index = i + 1
            
        self.cues = new_cues

    def get_srt(self) -> str:
        """
        Get the SRT formatted subtitles from the SubMaker object.

        Returns:
            str: The SRT formatted subtitles.
        """
        return srt.compose(self.cues) # type: ignore

    def __str__(self) -> str:
        return self.get_srt()