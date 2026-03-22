"""Pytest configuration for OpenKlerk tests."""
import pytest


@pytest.fixture
def sample_entity_data():
    """Sample business entity data for testing."""
    return {
        "entity_name": "Test Corporation",
        "entity_number": "C1234567",
        "entity_type": "corporation",
        "state_of_formation": "CA",
        "principal_address": {
            "street1": "123 Main St",
            "city": "San Francisco",
            "state": "CA",
            "zip": "94105",
        },
        "officers": [
            {
                "full_name": "Jane Doe",
                "title": "CEO",
                "email": "jane@test.com",
                "is_signer": True,
            },
            {
                "full_name": "John Smith",
                "title": "Secretary",
                "email": "john@test.com",
            },
        ],
        "portal_username": "test@example.com",
        "portal_password": "testpass",
    }


@pytest.fixture
def sample_context(sample_entity_data):
    """Sample FilingContext for testing."""
    from openklerk.core.base_filer import FilingContext
    return FilingContext(**sample_entity_data)
