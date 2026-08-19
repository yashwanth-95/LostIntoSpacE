"""Units, quantities and uncertainty propagation."""

import math

import pytest
from pydantic import ValidationError

from data.models import Dimension, Quantity, UnitError, convert, dimension_of, get_unit


class TestUnitRegistry:
    def test_aliases_resolve_to_canonical_symbol(self):
        assert get_unit("kilometers").symbol == "km"
        assert get_unit("DEGREES").symbol == "deg"
        assert get_unit("m s^-1").symbol == "m/s"
        assert get_unit("").symbol == "1"

    def test_unknown_unit_raises(self):
        with pytest.raises(UnitError, match="unknown unit"):
            get_unit("furlongs_per_fortnight")

    def test_dimension_lookup(self):
        assert dimension_of("M_earth") is Dimension.MASS
        assert dimension_of("au") is Dimension.LENGTH
        assert dimension_of("rev/day") is Dimension.ANGULAR_VELOCITY
        assert dimension_of("mag") is Dimension.MAGNITUDE


class TestConversion:
    def test_length_roundtrip(self):
        assert convert(1.0, "au", "km") == pytest.approx(1.495978707e8)
        assert convert(1.495978707e8, "km", "au") == pytest.approx(1.0)

    def test_temperature_is_affine(self):
        assert convert(0.0, "degC", "K") == pytest.approx(273.15)
        assert convert(-273.15, "degC", "K") == pytest.approx(0.0, abs=1e-9)
        assert convert(32.0, "degF", "degC") == pytest.approx(0.0, abs=1e-9)

    def test_angular_velocity(self):
        # One revolution per day in rad/s.
        assert convert(1.0, "rev/day", "rad/s") == pytest.approx(2 * math.pi / 86400.0)

    def test_dimension_mismatch_rejected(self):
        with pytest.raises(UnitError, match="different dimensions"):
            convert(1.0, "kg", "km")

    def test_magnitude_cannot_convert_to_ratio(self):
        """Magnitudes are logarithmic and must never silently become a ratio."""
        with pytest.raises(UnitError, match="different dimensions"):
            convert(5.0, "mag", "1")


class TestQuantity:
    def test_defaults_to_dimensionless(self):
        assert Quantity(value=0.5).unit == "1"
        assert Quantity(value=0.5).dimension is Dimension.DIMENSIONLESS

    def test_unit_is_canonicalized_on_construction(self):
        assert Quantity(value=1.0, unit="kilometres").unit == "km"

    def test_conversion_scales_symmetric_uncertainty(self):
        q = Quantity(value=6371.0, unit="km", uncertainty=2.0)
        converted = q.to("m")
        assert converted.value == pytest.approx(6_371_000.0)
        assert converted.uncertainty == pytest.approx(2000.0)

    def test_conversion_scales_asymmetric_uncertainty(self):
        q = Quantity(value=1.0, unit="R_jup", uncertainty_upper=0.05, uncertainty_lower=0.03)
        converted = q.to("R_earth")
        ratio = 7.1492e7 / 6.3781e6
        assert converted.uncertainty_upper == pytest.approx(0.05 * ratio)
        assert converted.uncertainty_lower == pytest.approx(0.03 * ratio)

    def test_affine_conversion_does_not_scale_uncertainty(self):
        """A degC->K shift moves the value but not the width of the error bar."""
        q = Quantity(value=20.0, unit="degC", uncertainty=1.5)
        converted = q.to("K")
        assert converted.value == pytest.approx(293.15)
        assert converted.uncertainty == pytest.approx(1.5)

    def test_to_si_uses_canonical_unit(self):
        assert Quantity(value=1.0, unit="g/cm3").to_si().unit == "kg/m3"
        assert Quantity(value=1.0, unit="g/cm3").si_value() == pytest.approx(1000.0)

    def test_approx_equals_is_unit_independent(self):
        a = Quantity(value=1.0, unit="au")
        b = Quantity(value=1.495978707e8, unit="km")
        assert a.approx_equals(b)

    def test_approx_equals_rejects_other_dimensions(self):
        assert not Quantity(value=1.0, unit="kg").approx_equals(Quantity(value=1.0, unit="km"))

    def test_dimension_mismatch_on_convert(self):
        with pytest.raises(UnitError):
            Quantity(value=1.0, unit="kg").to("km")

    def test_quantity_is_immutable(self):
        q = Quantity(value=1.0, unit="km")
        with pytest.raises(ValidationError):
            q.value = 2.0

    def test_str_includes_uncertainty_and_unit(self):
        assert "±" in str(Quantity(value=1.0, unit="km", uncertainty=0.1))
        assert str(Quantity(value=0.25)) == "0.25"


class TestQuantityMalformed:
    def test_nan_rejected(self):
        with pytest.raises(ValidationError, match="finite"):
            Quantity(value=float("nan"), unit="km")

    def test_infinity_rejected(self):
        with pytest.raises(ValidationError, match="finite"):
            Quantity(value=float("inf"), unit="km")

    def test_nan_uncertainty_rejected(self):
        # Caught by the `ge=0` bound before the finiteness check, since NaN
        # fails every comparison. Either way it cannot be constructed.
        with pytest.raises(ValidationError):
            Quantity(value=1.0, unit="km", uncertainty=float("nan"))

    def test_infinite_uncertainty_rejected(self):
        with pytest.raises(ValidationError, match="finite"):
            Quantity(value=1.0, unit="km", uncertainty=float("inf"))

    def test_negative_uncertainty_rejected(self):
        with pytest.raises(ValidationError):
            Quantity(value=1.0, unit="km", uncertainty=-1.0)

    def test_unknown_unit_rejected(self):
        with pytest.raises(ValidationError, match="unknown unit"):
            Quantity(value=1.0, unit="bananas")

    def test_mixed_uncertainty_styles_rejected(self):
        with pytest.raises(ValidationError, match="not both"):
            Quantity(value=1.0, unit="km", uncertainty=0.5, uncertainty_upper=0.5)

    def test_unexpected_field_rejected(self):
        with pytest.raises(ValidationError):
            Quantity(value=1.0, unit="km", sigma=0.5)

    def test_non_numeric_value_rejected(self):
        with pytest.raises(ValidationError):
            Quantity(value="six thousand", unit="km")


class TestQuantitySourceAttribution:
    def test_source_survives_conversion(self, jpl_source):
        q = Quantity(value=939.4, unit="km", uncertainty=0.2, source=jpl_source)
        converted = q.to("m")
        assert converted.source is not None
        assert converted.source.source_name == "jpl_sbdb"
        assert converted.source.source_record_id == "2000001"

    def test_with_source_returns_a_copy(self, jpl_source):
        q = Quantity(value=1.0, unit="km")
        attributed = q.with_source(jpl_source)
        assert q.source is None
        assert attributed.source == jpl_source

    def test_has_uncertainty_flag(self):
        assert not Quantity(value=1.0, unit="km").has_uncertainty
        assert Quantity(value=1.0, unit="km", uncertainty=0.0).has_uncertainty
        assert Quantity(value=1.0, unit="km", uncertainty_upper=0.1).has_uncertainty
