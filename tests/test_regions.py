"""Tests for the shared police-district → region mapping."""

import pytest

from src.common import regions


@pytest.mark.parametrize(
    "district,expected",
    [
        ("Københavns Politi", regions.REGION_HOVEDSTADEN),
        ("Københavns Vestegns Politi", regions.REGION_HOVEDSTADEN),
        ("Nordsjællands Politi", regions.REGION_HOVEDSTADEN),
        ("Bornholms Politi", regions.REGION_HOVEDSTADEN),
        ("Midt- og Vestsjællands Politi", regions.REGION_SJAELLAND),
        ("Sydsjællands og Lolland-Falsters Politi", regions.REGION_SJAELLAND),
        ("Fyns Politi", regions.REGION_FYN),
        ("Nordjyllands Politi", regions.REGION_JYLLAND),
        ("Midt- og Vestjyllands Politi", regions.REGION_JYLLAND),
        ("Østjyllands Politi", regions.REGION_JYLLAND),
        ("Sydøstjyllands Politi", regions.REGION_JYLLAND),
        ("Syd- og Sønderjyllands Politi", regions.REGION_JYLLAND),
    ],
)
def test_district_to_region(district, expected):
    assert regions.district_to_region(district) == expected


def test_prosecutor_prefix_resolves():
    # "Anklagemyndigheden ved X Politi" carries the district as a substring.
    assert (
        regions.district_to_region("Anklagemyndigheden ved Østjyllands Politi")
        == regions.REGION_JYLLAND
    )


def test_case_insensitive():
    assert regions.district_to_region("nordjyllands politi") == regions.REGION_JYLLAND


def test_national_entities():
    assert regions.district_to_region("Rigspolitiet") == regions.REGION_NATIONAL
    assert (
        regions.district_to_region("National enhed for Særlig Kriminalitet")
        == regions.REGION_NATIONAL
    )
    assert regions.district_to_region("Politiskolen") == regions.REGION_NATIONAL


def test_unknown_and_empty():
    assert regions.district_to_region("") is None
    assert regions.district_to_region("Ukendt Politi") is None


def test_regions_list_is_canonical_order_without_national():
    assert regions.REGIONS == [
        regions.REGION_HOVEDSTADEN,
        regions.REGION_SJAELLAND,
        regions.REGION_JYLLAND,
        regions.REGION_FYN,
    ]
    assert regions.REGION_NATIONAL not in regions.REGIONS
