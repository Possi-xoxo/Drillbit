import math
from app.physical import (Orientation, calculate_page_layout, drills_from_physical,
                          finished_size_mm, inches_to_mm, mm_to_inches, tile_ranges)

def test_100_square_physical_size():
    width_mm,height_mm=finished_size_mm(100,100,2.5)
    assert (width_mm,height_mm)==(250,250)
    assert math.isclose(mm_to_inches(width_mm),9.842519685,rel_tol=1e-8)

def test_unit_conversions():
    assert math.isclose(inches_to_mm(1),25.4)
    assert math.isclose(mm_to_inches(25.4),1)

def test_physical_size_rounds_to_whole_drills():
    assert drills_from_physical(10,12.5,"cm",2.5)==(40,50)
    assert drills_from_physical(10,10,"in",2.5)==(102,102)

def test_small_pattern_stays_one_sheet():
    layout=calculate_page_layout(50,50,2.5,Orientation.AUTO)
    assert layout.tile_count==1

def test_large_pattern_tiles_correctly():
    layout=calculate_page_layout(200,200,2.5,Orientation.PORTRAIT)
    assert (layout.columns,layout.rows,layout.tile_count)==(3,2,6)
    assert len(list(tile_ranges(200,200,layout)))==6

def test_auto_orientation_minimizes_page_count():
    portrait=calculate_page_layout(105,70,2.5,Orientation.PORTRAIT)
    auto=calculate_page_layout(105,70,2.5,Orientation.AUTO)
    assert auto.tile_count<=portrait.tile_count
    assert auto.orientation==Orientation.LANDSCAPE
