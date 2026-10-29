"""Original slide identity, independent of PDF geometry."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Slide:
    number: int
    title: str = ""

    def __post_init__(self):
        if type(self.number) is not int or not 1 <= self.number <= 20000 or not isinstance(self.title, str) or len(self.title) > 1024:
            raise ValueError("invalid slide")

    def to_dto(self):
        return {"number": self.number, "title": self.title}


def slide_of(row):
    number = row.get("slide_number_int")
    if number is None:
        return None
    try:
        return Slide(number, row.get("slide_title_kwd", "")).to_dto()
    except (TypeError, ValueError):
        return None
