import pytest
from validators import is_valid_project_id, is_valid_dataset_name

class TestValidators:
    def test_project_id_valid(self):
        assert is_valid_project_id("my-project-123") is True
        assert is_valid_project_id("a12345") is True # Minimum 6 chars
        assert is_valid_project_id("a" * 30) is True # Max 30 chars

    def test_project_id_invalid(self):
        assert is_valid_project_id("") is False # Empty
        assert is_valid_project_id("1my-project") is False # Must start with letter
        assert is_valid_project_id("my_project") is False # Underscores not allowed
        assert is_valid_project_id("my-project-") is False # Cannot end with hyphen
        assert is_valid_project_id("my-Project-123") is False # Uppercase not allowed
        assert is_valid_project_id("a1234") is False # Too short (5)
        assert is_valid_project_id("a" * 31) is False # Too long (31)

    def test_dataset_name_valid(self):
        assert is_valid_dataset_name("my_dataset") is True
        assert is_valid_dataset_name("dataset123") is True
        assert is_valid_dataset_name("Dataset_NAME") is True
        assert is_valid_dataset_name("A") is True

    def test_dataset_name_invalid(self):
        assert is_valid_dataset_name("") is False # Empty
        assert is_valid_dataset_name("my-dataset") is False # Hyphens not allowed
        assert is_valid_dataset_name("my dataset") is False # Spaces not allowed
        assert is_valid_dataset_name("data!set") is False # Special chars not allowed
