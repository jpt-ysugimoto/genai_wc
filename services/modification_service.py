import pickle
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ModificationService:
    def __init__(self, mod_filepath: Path):
        """
        Initialize the ModificationService.

        Parameters
        ----------
        mod_filepath : Path
            The file path to store modifications.
        """
        self.mod_filepath = mod_filepath

    def load_modifications(self) -> list:
        """
        Load modifications from a pickle file.

        Returns
        -------
        list
            A list of modifications.
        """
        if not self.mod_filepath.exists():
            logger.info(
                f"No modifications file found at {self.mod_filepath}. Starting with an empty list."
            )
            return []

        try:
            with self.mod_filepath.open("rb") as file:
                modifications = pickle.load(file)
            if not isinstance(modifications, list):
                logger.error(f"Invalid format in {self.mod_filepath}. Expected a list.")
                return []
            logger.info(
                f"Loaded {len(modifications)} modifications from {self.mod_filepath}."
            )
            return modifications
        except Exception as e:
            logger.error(f"Failed to load modifications from {self.mod_filepath}: {e}")
            return []

    def save_modifications(self, modification):
        """
        Save a single modification to a pickle file by appending it to a list of modifications.

        Parameters
        ----------
        modification : str
            A single modification string to save.
        """
        modifications = self.load_modifications()
        modifications.append(modification)

        try:
            with self.mod_filepath.open("wb") as file:
                pickle.dump(modifications, file)
            logger.info(f"Saved modification to {self.mod_filepath}.")
        except Exception as e:
            logger.error(f"Failed to save modifications to {self.mod_filepath}: {e}")
