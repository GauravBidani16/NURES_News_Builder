"""Pytest configuration and global fixtures."""

import os

# Set test environment defaults before any module imports
os.environ["APP_ENV"] = "test"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_API_KEY"] = "mock-key-for-tests"
