from abc import ABC, abstractmethod
from pathlib import Path

from ..errors import InvalidInputError
from ..models import DocumentStructure


class BaseParser(ABC):
    """Abstract base class for all DeepDoc parsers."""
    
    @abstractmethod
    def parse(self, file_path: Path) -> DocumentStructure:
        """
        Parse the input file and extract its logical document structure.
        
        Args:
            file_path (Path): Path to the input file.
            
        Returns:
            DocumentStructure: The standardized parsed document content.
            
        Raises:
            InvalidInputError: If the file does not exist or is unreadable.
            ParsingFailureError: If an error occurs during parsing.
            UnsupportedFormatError: If the file format is unsupported by the implementation.
        """
        
    def _validate_file(self, file_path: Path):
        """Helper to ensure the file exists and is a file."""
        if not file_path.exists():
            raise InvalidInputError(f"File not found: {file_path}")
        if not file_path.is_file():
            raise InvalidInputError(f"Path is not a file: {file_path}")
