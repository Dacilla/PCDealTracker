# backend/tests/test_parsing.py
import pytest
import os
from backend.app.utils.parsing import (
    parse_product_name,
    normalize_model_strict,
    normalize_model_loose,
    parse_product_attributes
)

# --- Tests for parse_product_name ---

def test_parse_product_name_finds_brand_and_model():
    """Tests that the function correctly separates brand and model."""
    name = "ASUS ROG Strix GeForce RTX 4090 OC Edition 24GB GDDR6X"
    result = parse_product_name(name)
    assert result["brand"] == "ASUS"
    assert result["model"] == "ROG Strix GeForce RTX 4090 OC Edition 24GB GDDR6X"

def test_parse_product_name_handles_no_brand():
    """Tests that the model remains the full name if no known brand is found."""
    name = "Some Unknown Brand RTX 3080"
    result = parse_product_name(name)
    assert result["brand"] is None
    assert result["model"] == "Some Unknown Brand RTX 3080"

# --- Tests for Normalization ---

@pytest.mark.parametrize("input_string, expected_output", [
    ("Core i9-13900K Processor with Cooler", "core i9-13900k"),
    ("Ryzen 9 7950X3D Gaming CPU", "ryzen 9 7950x3d"),
    ("GeForce RTX 4070 Ti SUPER 16GB GDDR6X", "geforce rtx 4070 ti super 16"),
])
def test_normalize_model_strict(input_string, expected_output):
    """Tests the strict normalization function."""
    assert normalize_model_strict(input_string) == expected_output

@pytest.mark.parametrize("input_string, expected_output", [
    ("Intel Core i9-13900K 3.0GHz 24-Core Processor", "intel i9-13900k"),
    ("AMD Ryzen 7 7800X3D 8-Core AM5 CPU", "amd ryzen 7 7800x3d am5"),
])
def test_normalize_model_loose(input_string, expected_output):
    """Tests the more aggressive loose normalization."""
    assert normalize_model_loose(input_string) == expected_output

# --- Tests for Attribute Parsing by Category ---

def test_parse_attributes_cpu():
    """Tests attribute parsing for CPUs."""
    name = "Intel Core i7-14700K LGA1700 Desktop Processor"
    attrs = parse_product_attributes(name, "CPUs")
    assert attrs["socket"] == "LGA1700"
    assert attrs["intel_series"] == "Core i7"

    name_amd = "AMD Ryzen 9 7900X AM5 12-Core 4.7GHz CPU Processor"
    attrs_amd = parse_product_attributes(name_amd, "CPUs")
    assert attrs_amd["socket"] == "AM5"
    assert attrs_amd["amd_series"] == "Ryzen 9"

def test_parse_attributes_gpu():
    """Tests attribute parsing for Graphics Cards."""
    name = "Gigabyte GeForce RTX 4070 SUPER Gaming OC 12GB Video Card"
    attrs = parse_product_attributes(name, "Graphics Cards")
    assert attrs["vram_gb"] == 12
    assert attrs["series"] == "RTX"

def test_parse_attributes_motherboard():
    """Tests attribute parsing for Motherboards."""
    name = "MSI B760M GAMING PLUS WIFI Micro-ATX LGA1700 Motherboard"
    attrs = parse_product_attributes(name, "Motherboards")
    assert attrs["socket"] == "LGA1700"
    assert attrs["form_factor"] == "Micro-ATX"
    assert attrs["intel_chipset"] == "B760"

    name_amd = "ASRock X670E PG Lightning AM5 E-ATX Motherboard"
    attrs_amd = parse_product_attributes(name_amd, "Motherboards")
    assert attrs_amd["socket"] == "AM5"
    assert attrs_amd["form_factor"] == "E-ATX"
    assert attrs_amd["amd_chipset"] == "X670E"
    
def test_parse_attributes_ram():
    """Tests attribute parsing for Memory (RAM)."""
    name = "Corsair Vengeance 32GB (2x16GB) DDR5 6000MHz CL36 SODIMM Memory"
    attrs = parse_product_attributes(name, "Memory (RAM)")
    assert attrs["type"] == "DDR5"
    assert attrs["capacity_gb"] == 32
    assert attrs["speed_mhz"] == 6000
    assert attrs["form_factor"] == "SODIMM"
    assert attrs["ecc"] == "Non-ECC"

def test_parse_attributes_storage():
    """Tests attribute parsing for Storage (SSD/HDD)."""
    name_nvme = "Samsung 990 Pro 2TB M.2 NVMe PCIe 4.0 SSD"
    attrs_nvme = parse_product_attributes(name_nvme, "Storage (SSD/HDD)")
    assert attrs_nvme["type"] == "NVMe SSD"
    assert attrs_nvme["capacity_gb"] == 2000
    assert attrs_nvme["form_factor"] == "M.2"

    name_hdd = "Seagate IronWolf 8TB 3.5in SATA Hard Drive for NAS"
    attrs_hdd = parse_product_attributes(name_hdd, "Storage (SSD/HDD)")
    assert attrs_hdd["type"] == "HDD"
    assert attrs_hdd["capacity_gb"] == 8000
    assert attrs_hdd["form_factor"] == '3.5"'

def test_parse_attributes_psu():
    """Tests attribute parsing for Power Supplies."""
    name = "Seasonic FOCUS Plus Gold 850W Fully Modular Power Supply"
    
    # Set the environment variable to enable debug printing for this test
    os.environ["DEBUG_PARSING"] = "True"
    attrs = parse_product_attributes(name, "Power Supplies")
    # Unset the variable immediately after to avoid affecting other tests
    os.environ.pop("DEBUG_PARSING", None)

    assert attrs["wattage"] == 850
    assert attrs["rating"] == "80+ Gold"
    assert attrs["modularity"] == "Fully Modular"

def test_parse_attributes_case():
    """Tests attribute parsing for PC Cases."""
    name = "Lian Li PC-O11 Dynamic EVO Mid Tower Case - Black"
    attrs = parse_product_attributes(name, "PC Cases")
    assert attrs["size"] == "Mid Tower"

def test_parse_attributes_cooler():
    """Tests attribute parsing for Cooling."""
    name_aio = "Corsair iCUE H150i ELITE CAPELLIX XT 360mm AIO Liquid CPU Cooler"
    attrs_aio = parse_product_attributes(name_aio, "Cooling")
    assert attrs_aio["type"] == "Liquid Cooler"

    name_air = "Noctua NH-D15 Chromax Black Dual Tower CPU Air Cooler"
    attrs_air = parse_product_attributes(name_air, "Cooling")
    assert attrs_air["type"] == "Air Cooler"

def test_parse_attributes_monitor():
    """Tests attribute parsing for Monitors."""
    name = 'LG UltraGear 27GR95QE-B 27" 240Hz 1440p QHD OLED Gaming Monitor'
    attrs = parse_product_attributes(name, "Monitors")
    assert attrs["screen_size_inch"] == 27
    assert attrs["resolution"] == "1440p"
    assert attrs["panel_type"] == "OLED"
    assert attrs["refresh_rate_hz"] == 240
