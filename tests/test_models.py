import pytest
from app.models import ConversionSettings

@pytest.mark.parametrize("width,height", [(9, 100), (1001, 100), (100, 9), (100, 1001)])
def test_invalid_dimensions(width, height):
    with pytest.raises(ValueError): ConversionSettings(width=width, height=height).validate()
