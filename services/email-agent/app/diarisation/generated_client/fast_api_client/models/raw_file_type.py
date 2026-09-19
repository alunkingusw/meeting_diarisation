from enum import StrEnum


class RawFileType(StrEnum):
    AUDIO = "audio"
    TRANSCRIPT_GENERATED = "transcript_generated"
    TRANSCRIPT_PROVIDED = "transcript_provided"

    def __str__(self) -> str:
        return str(self.value)
