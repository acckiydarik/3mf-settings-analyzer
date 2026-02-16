"""Shared pytest fixtures for 3MF Settings Analyzer tests."""

import json
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    """Alias for pytest's built-in tmp_path fixture."""
    return tmp_path


@pytest.fixture
def sample_project_settings() -> dict:
    """Sample project_settings.config content as dict."""
    return {
        "printer_settings_id": "Bambu Lab A1 mini 0.4 nozzle",
        "print_settings_id": "0.20mm Standard @BBL A1M",
        "filament_settings_id": ["Bambu PLA Basic @BBL A1M"],
        "layer_height": "0.2",
        "initial_layer_print_height": "0.2",
        "line_width": "0.42",
        "wall_loops": "3",
        "sparse_infill_density": "15%",
        "brim_type": "no_brim",
        "enable_support": "0",
        "outer_wall_speed": "200",
        "inner_wall_speed": "300",
        "sparse_infill_speed": "270",
        "top_surface_speed": "200",
        "travel_speed": "700",
        "bridge_speed": "50",
        "top_shell_layers": "5",
        "bottom_shell_layers": "3",
        "seam_position": "back",
        "sparse_infill_pattern": "gyroid",
        "top_surface_pattern": "monotonicline",
        "print_sequence": "by layer",
        "retraction_length": "0.8",
        "retraction_speed": "30",
        "z_hop": "0.4",
        "fan_min_speed": "60",
        "fan_max_speed": "80",
        "nozzle_temperature": "220",
        "hot_plate_temp": "60",
        "different_settings_to_system": ["wall_loops;seam_position"],
    }


@pytest.fixture
def sample_model_settings_xml() -> str:
    """Sample model_settings.config XML content."""
    return '''<?xml version="1.0" encoding="UTF-8"?>
<config>
    <plate>
        <metadata key="plater_id" value="1"/>
        <metadata key="plater_name" value="Plate 1"/>
        <model_instance>
            <metadata key="object_id" value="1"/>
            <metadata key="identify_id" value="0"/>
        </model_instance>
    </plate>
    <object id="1">
        <metadata key="name" value="TestObject"/>
        <metadata key="extruder" value="1"/>
        <metadata key="wall_loops" value="4"/>
        <part id="0" subtype="normal_part">
            <metadata key="name" value="TestPart"/>
            <metadata key="extruder" value="1"/>
        </part>
    </object>
</config>
'''


@pytest.fixture
def sample_3mf(temp_dir: Path, sample_project_settings: dict, sample_model_settings_xml: str) -> Path:
    """Create a valid sample 3MF file for testing."""
    threemf_path = temp_dir / "test.3mf"
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        # Create Metadata directory and files
        zf.writestr("Metadata/project_settings.config", json.dumps(sample_project_settings))
        zf.writestr("Metadata/model_settings.config", sample_model_settings_xml)
        # Add a dummy model file for completeness
        zf.writestr("3D/model.model", "<model></model>")
    
    return threemf_path


@pytest.fixture
def malicious_3mf_absolute_path(temp_dir: Path) -> Path:
    """Create a malicious 3MF file with absolute path (Zip Slip attack)."""
    threemf_path = temp_dir / "malicious_absolute.3mf"
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        # Absolute path - should be rejected
        zf.writestr("/etc/passwd", "malicious content")
    
    return threemf_path


@pytest.fixture  
def malicious_3mf_traversal(temp_dir: Path) -> Path:
    """Create a malicious 3MF file with path traversal (Zip Slip attack)."""
    threemf_path = temp_dir / "malicious_traversal.3mf"
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        # Path traversal - should be rejected
        zf.writestr("../../../etc/passwd", "malicious content")
    
    return threemf_path


@pytest.fixture
def empty_3mf(temp_dir: Path) -> Path:
    """Create an empty 3MF file (no configs)."""
    threemf_path = temp_dir / "empty.3mf"
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        zf.writestr("3D/model.model", "<model></model>")
    
    return threemf_path


@pytest.fixture
def invalid_json_3mf(temp_dir: Path, sample_model_settings_xml: str) -> Path:
    """Create a 3MF file with invalid JSON in project_settings."""
    threemf_path = temp_dir / "invalid_json.3mf"
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        zf.writestr("Metadata/project_settings.config", "{invalid json content")
        zf.writestr("Metadata/model_settings.config", sample_model_settings_xml)
    
    return threemf_path


@pytest.fixture
def invalid_xml_3mf(temp_dir: Path, sample_project_settings: dict) -> Path:
    """Create a 3MF file with invalid XML in model_settings."""
    threemf_path = temp_dir / "invalid_xml.3mf"
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        zf.writestr("Metadata/project_settings.config", json.dumps(sample_project_settings))
        zf.writestr("Metadata/model_settings.config", "<config><unclosed>")
    
    return threemf_path


@pytest.fixture
def sample_printconfig_cpp() -> str:
    """Sample PrintConfig.cpp snippet for parser testing."""
    return '''
    def = this->add("layer_height", coFloat);
    def->label = L("Layer height");
    def->category = L("Quality");
    def->tooltip = L("Layer height is the depth of each layer of filament deposited.");
    def->sidetext = L("mm");
    def->set_default_value(new ConfigOptionFloat(0.2));

    def = this->add("wall_loops", coInt);
    def->label = L("Wall loops");
    def->full_label = L("Number of wall loops");
    def->category = L("Strength");
    def->tooltip = L("Number of perimeter walls.");
    def->set_default_value(new ConfigOptionInt(2));

    def = this->add("enable_support", coBool);
    def->label = L("Enable support");
    def->category = L("Support");
    def->set_default_value(new ConfigOptionBool(false));
'''


@pytest.fixture
def sample_tab_cpp() -> str:
    """Sample Tab.cpp snippet for parser testing."""
    return '''
    optgroup->append_single_option_line("layer_height", "quality_settings_layer_height");
    optgroup->append_single_option_line("wall_loops", "quality_settings_walls");
    
    Line line = optgroup->create_option_line(m_config->get_option("enable_support"));
    line.label_path = "support_settings_enable";
    line.append_option(optgroup->get_option("support_type"));
    optgroup->append_line(line);
'''


@pytest.fixture
def multi_plate_3mf(temp_dir: Path, sample_project_settings: dict) -> Path:
    """Create a 3MF file with multiple plates."""
    threemf_path = temp_dir / "multi_plate.3mf"
    
    model_settings_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<config>
    <plate>
        <metadata key="plater_id" value="1"/>
        <metadata key="plater_name" value="Plate 1"/>
        <model_instance>
            <metadata key="object_id" value="1"/>
            <metadata key="identify_id" value="0"/>
        </model_instance>
    </plate>
    <plate>
        <metadata key="plater_id" value="2"/>
        <metadata key="plater_name" value="Plate 2"/>
        <model_instance>
            <metadata key="object_id" value="2"/>
            <metadata key="identify_id" value="0"/>
        </model_instance>
        <model_instance>
            <metadata key="object_id" value="3"/>
            <metadata key="identify_id" value="1"/>
        </model_instance>
    </plate>
    <object id="1">
        <metadata key="name" value="Object_Plate1"/>
        <metadata key="extruder" value="1"/>
    </object>
    <object id="2">
        <metadata key="name" value="Object_Plate2_First"/>
        <metadata key="extruder" value="1"/>
    </object>
    <object id="3">
        <metadata key="name" value="Object_Plate2_Second"/>
        <metadata key="extruder" value="1"/>
    </object>
</config>
'''
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        zf.writestr("Metadata/project_settings.config", json.dumps(sample_project_settings))
        zf.writestr("Metadata/model_settings.config", model_settings_xml)
        zf.writestr("3D/model.model", "<model></model>")
    
    return threemf_path


@pytest.fixture
def multi_part_object_3mf(temp_dir: Path, sample_project_settings: dict) -> Path:
    """Create a 3MF file with an object containing multiple parts."""
    threemf_path = temp_dir / "multi_part.3mf"
    
    model_settings_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<config>
    <plate>
        <metadata key="plater_id" value="1"/>
        <metadata key="plater_name" value="Plate 1"/>
        <model_instance>
            <metadata key="object_id" value="1"/>
            <metadata key="identify_id" value="0"/>
        </model_instance>
    </plate>
    <object id="1">
        <metadata key="name" value="MultiPartObject"/>
        <metadata key="extruder" value="1"/>
        <metadata key="wall_loops" value="3"/>
        <part id="0" subtype="normal_part">
            <metadata key="name" value="PartA"/>
            <metadata key="extruder" value="1"/>
            <metadata key="sparse_infill_density" value="30%"/>
        </part>
        <part id="1" subtype="normal_part">
            <metadata key="name" value="PartB"/>
            <metadata key="extruder" value="2"/>
            <metadata key="sparse_infill_density" value="50%"/>
        </part>
        <part id="2" subtype="normal_part">
            <metadata key="name" value="PartC"/>
            <metadata key="extruder" value="1"/>
        </part>
    </object>
</config>
'''
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        zf.writestr("Metadata/project_settings.config", json.dumps(sample_project_settings))
        zf.writestr("Metadata/model_settings.config", model_settings_xml)
        zf.writestr("3D/model.model", "<model></model>")
    
    return threemf_path


@pytest.fixture
def unicode_names_3mf(temp_dir: Path, sample_project_settings: dict) -> Path:
    """Create a 3MF file with Unicode object and part names."""
    threemf_path = temp_dir / "unicode_names.3mf"
    
    model_settings_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<config>
    <plate>
        <metadata key="plater_id" value="1"/>
        <metadata key="plater_name" value="Пластина 1"/>
        <model_instance>
            <metadata key="object_id" value="1"/>
            <metadata key="identify_id" value="0"/>
        </model_instance>
    </plate>
    <object id="1">
        <metadata key="name" value="Тестовый_Объект_测试"/>
        <metadata key="extruder" value="1"/>
        <part id="0" subtype="normal_part">
            <metadata key="name" value="Часть_日本語"/>
            <metadata key="extruder" value="1"/>
        </part>
    </object>
</config>
'''
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        zf.writestr("Metadata/project_settings.config", json.dumps(sample_project_settings))
        zf.writestr("Metadata/model_settings.config", model_settings_xml)
        zf.writestr("3D/model.model", "<model></model>")
    
    return threemf_path


@pytest.fixture
def empty_list_settings_3mf(temp_dir: Path, sample_model_settings_xml: str) -> Path:
    """Create a 3MF file with empty list values in settings."""
    threemf_path = temp_dir / "empty_list.3mf"
    
    settings = {
        "printer_settings_id": "Test Printer",
        "print_settings_id": "Test Process",
        "filament_settings_id": [],  # Empty list
        "different_settings_to_system": [],
    }
    
    with zipfile.ZipFile(threemf_path, 'w') as zf:
        zf.writestr("Metadata/project_settings.config", json.dumps(settings))
        zf.writestr("Metadata/model_settings.config", sample_model_settings_xml)
        zf.writestr("3D/model.model", "<model></model>")
    
    return threemf_path


# ═══════════════════════════════════════════════════════════════
# Gcode fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def sample_gcode_content() -> str:
    """Sample gcode file content for testing."""
    return """; HEADER_BLOCK_START
; generated by Snapmaker Orca 2.2.1 on 2026-01-30 at 12:34:13
; total layer number: 138
; filament_density: 1.24,1.24,1.24
; filament_diameter: 1.75,1.75,1.75
; max_z_height: 22.12
; HEADER_BLOCK_END

; THUMBNAIL_BLOCK_START
; some thumbnail data
; THUMBNAIL_BLOCK_END

; EXECUTABLE_BLOCK_START
G28 ; home all axes
G1 Z5 F3000 ; lift nozzle
M104 S220 ; set extruder temp
M140 S60 ; set bed temp
M109 S220 ; wait for extruder temp
M190 S60 ; wait for bed temp

; printing object TestModel.stl id:123456789 copy 0
G1 X50 Y50 Z0.2 F3000
G1 X100 E10 F1500
; printing object TestModel.stl id:123456789 copy 0

; printing object SecondObject.stl id:987654321 copy 0
G1 X150 Y150 Z0.2 F3000
G1 X200 E20 F1500
; printing object SecondObject.stl id:987654321 copy 0

; filament used [g] = 10.08, 0.87, 0.31
; filament cost = 0.20, 0.02, 0.01
; total filament used [g] = 11.26
; total filament cost = 0.23
; total filament change = 2
; estimated printing time (normal mode) = 1h 11m 17s
; estimated first layer printing time (normal mode) = 2m 30s
; total layers count = 138

; CONFIG_BLOCK_START
; printer_settings_id = Snapmaker U1 (0.4 nozzle)
; print_settings_id = 0.16 High Quality @Snapmaker U1 (0.4 nozzle)
; filament_settings_id = "Snapmaker PLA SnapSpeed @U1";"Snapmaker PETG @U1"
; filament_type = PLA;PETG
; filament_colour = #DE1619FF;#FFFFFFFF
; layer_height = 0.16
; first_layer_height = 0.200
; nozzle_diameter = 0.4,0.4,0.4,0.4
; wall_loops = 3
; sparse_infill_density = 15%
; brim_type = no_brim
; enable_support = 0
; outer_wall_speed = 200
; inner_wall_speed = 300
; travel_speed = 700
; first_layer_bed_temperature = 65
; first_layer_temperature = 220
; different_settings_to_system = wall_loops;sparse_infill_density
; printer_model = Snapmaker U1
; gcode_flavor = marlin
; nozzle_type = hardened_steel
; curr_bed_type = Engineering Plate
; filament_vendor = "Snapmaker";"eSUN"
; enable_prime_tower = 0
; CONFIG_BLOCK_END
"""


@pytest.fixture
def sample_gcode(temp_dir: Path, sample_gcode_content: str) -> Path:
    """Create a sample gcode file for testing."""
    gcode_path = temp_dir / "test_model.gcode"
    gcode_path.write_text(sample_gcode_content, encoding='utf-8')
    return gcode_path


@pytest.fixture
def empty_gcode(temp_dir: Path) -> Path:
    """Create an empty gcode file."""
    gcode_path = temp_dir / "empty.gcode"
    gcode_path.write_text("", encoding='utf-8')
    return gcode_path


@pytest.fixture
def minimal_gcode(temp_dir: Path) -> Path:
    """Create a minimal gcode file without CONFIG_BLOCK."""
    gcode_path = temp_dir / "minimal.gcode"
    gcode_path.write_text("""G28 ; home
G1 X100 Y100 Z0.2 F3000
G1 X150 E10 F1500
""", encoding='utf-8')
    return gcode_path


@pytest.fixture
def gcode_no_objects(temp_dir: Path) -> Path:
    """Create a gcode file without object markers."""
    gcode_path = temp_dir / "no_objects.gcode"
    gcode_path.write_text("""; HEADER_BLOCK_START
; generated by Snapmaker Orca 2.2.1 on 2026-01-30 at 12:34:13
; total layer number: 50
; HEADER_BLOCK_END

G28
G1 X100 Y100 Z0.2 F3000

; total layers count = 50
; estimated printing time (normal mode) = 30m 15s

; CONFIG_BLOCK_START
; printer_settings_id = Test Printer
; print_settings_id = Test Process
; layer_height = 0.2
; CONFIG_BLOCK_END
""", encoding='utf-8')
    return gcode_path


@pytest.fixture
def gcode_unicode_objects(temp_dir: Path) -> Path:
    """Create a gcode file with Unicode object names."""
    gcode_path = temp_dir / "unicode_objects.gcode"
    gcode_path.write_text("""; HEADER_BLOCK_START
; generated by Snapmaker Orca 2.2.1 on 2026-01-30 at 12:34:13
; total layer number: 100
; HEADER_BLOCK_END

; printing object Тестовый_Объект_测试.stl id:123 copy 0
G1 X100 Y100 Z0.2 F3000

; CONFIG_BLOCK_START
; printer_settings_id = Test Printer
; print_settings_id = Test Process
; CONFIG_BLOCK_END
""", encoding='utf-8')
    return gcode_path
