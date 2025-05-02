import arcpy
import os
from datetime import datetime

# ---------------------------------------------------------------------
# Using references from current .aprx project
# ---------------------------------------------------------------------
shapefile = "Wildomar Shapefile"  # Reference to layer in current .aprx
table = "Wildomar Table"  # Reference to table in current .aprx

# Set workspace for output
output_folder = os.path.dirname(arcpy.Describe(shapefile).catalogPath)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
lower_output = os.path.join(output_folder, f"PCI_Below_{timestamp}.shp")
higher_output = os.path.join(output_folder, f"PCI_Above_{timestamp}.shp")
combined_output = os.path.join(output_folder, f"PCI_All_{timestamp}.shp")

# New midpoint shapefiles
lower_midpoints = os.path.join(output_folder, f"PCI_Below_Mid_{timestamp}.shp")
higher_midpoints = os.path.join(output_folder, f"PCI_Above_Mid_{timestamp}.shp")
combined_midpoints = os.path.join(output_folder, f"PCI_All_Mid_{timestamp}.shp")

# ---------------------------------------------------------------------
# Input thresholds for PCI differences
# ---------------------------------------------------------------------
# Get user input for thresholds
lower_threshold = input("Enter lower threshold for PCI difference (results <= this value will be flagged): ")
higher_threshold = input("Enter higher threshold for PCI difference (results >= this value will be flagged): ")

# Convert to integers
try:
    lower_threshold = int(lower_threshold)
    higher_threshold = int(higher_threshold)
except ValueError:
    print("❌ Error: Thresholds must be numeric values. Using defaults of -10 and 10.")
    lower_threshold = -10
    higher_threshold = 10

print(f"\nUsing:\n  • Shapefile: {shapefile}\n  • Table: {table}")
print(f"  • Lower Threshold (≤): {lower_threshold}\n  • Higher Threshold (≥): {higher_threshold}")
print(f"  • Combined Output: {combined_output}")
print(f"  • Lower Output: {lower_output}\n  • Higher Output: {higher_output}")
print(f"  • Midpoint Outputs: {combined_midpoints}, {lower_midpoints}, {higher_midpoints}")

# ---------------------------------------------------------------------
# Helper function to check if a field exists and get field names
# ---------------------------------------------------------------------
def get_existing_fields(fc):
    """Return a list of all field names in a feature class, converted to uppercase"""
    return [field.name.upper() for field in arcpy.ListFields(fc)]

def add_field_if_not_exists(fc, field_name, field_type, **kwargs):
    """Add a field if it doesn't already exist, using case-insensitive check
    Also handles truncating field names for shapefile compatibility"""
    
    existing_fields = get_existing_fields(fc)
    
    # For shapefiles, truncate field name to 10 characters if longer
    desc = arcpy.Describe(fc)
    if hasattr(desc, 'dataType') and desc.dataType == 'ShapeFile':
        orig_field_name = field_name
        field_name = field_name[:10]
        if orig_field_name != field_name:
            print(f"Truncated field name from {orig_field_name} to {field_name} for shapefile compatibility")
    
    if field_name.upper() not in existing_fields:
        try:
            arcpy.AddField_management(fc, field_name, field_type, **kwargs)
            return True
        except Exception as e:
            print(f"Error adding field {field_name}: {e}")
            return False
    return False

def get_safe_field_names(fc, needed_fields):
    """Get list of field names that actually exist in the feature class"""
    existing_fields_map = {field.name.upper(): field.name for field in arcpy.ListFields(fc)}
    result = ["FID"]  # Always include FID
    
    for field in needed_fields:
        # For shapefiles, check both original and truncated field names
        if field.upper() in existing_fields_map:
            result.append(existing_fields_map[field.upper()])
        elif field[:10].upper() in existing_fields_map:  # Check truncated version
            result.append(existing_fields_map[field[:10].upper()])
    
    return result

# Create field name mapping for shapefiles
def create_field_mapping(original_fields):
    """Create a mapping from original field names to shapefile-compatible names"""
    mapping = {}
    for field in original_fields:
        truncated = field[:10]
        mapping[field] = truncated
    return mapping

# ---------------------------------------------------------------------
# Helper function to create midpoint shapefiles
# ---------------------------------------------------------------------
def create_midpoint_shapefile(input_fc, output_fc):
    """Create a new point shapefile containing the midpoints of the lines in the input shapefile."""
    if not arcpy.Exists(input_fc):
        print(f"❌ Input shapefile {input_fc} does not exist. Skipping midpoint creation.")
        return
        
    try:
        print(f"\nCreating midpoint shapefile from {input_fc}...")
        
        # Delete output if it exists
        if arcpy.Exists(output_fc):
            arcpy.Delete_management(output_fc)
            
        # Get spatial reference from input
        spatial_ref = arcpy.Describe(input_fc).spatialReference
        
        # Create a temporary feature class for the midpoints
        arcpy.env.workspace = os.path.dirname(output_fc)
        temp_midpoints = "temp_midpoints"
        
        # Try multiple methods to create midpoints
        methods_to_try = [
            "feature_to_point",  # Method 1: Use FeatureToPoint (most reliable)
            "manual"             # Method 2: Calculate manually
        ]
        
        success = False
        point_count = 0
        
        for method in methods_to_try:
            if success:
                break
                
            if method == "feature_to_point":
                try:
                    print("Using FeatureToPoint to create midpoints with centroid option...")
                    
                    # Clean up any existing temporary data
                    if arcpy.Exists(temp_midpoints):
                        arcpy.Delete_management(temp_midpoints)
                    
                    # Try FeatureToPoint with CENTROID option
                    arcpy.FeatureToPoint_management(
                        input_fc,
                        temp_midpoints,
                        "CENTROID"  # Use CENTROID option
                    )
                    
                    # Check if any points were created
                    point_count = int(arcpy.GetCount_management(temp_midpoints).getOutput(0))
                    print(f"Created {point_count} midpoints using centroid method.")
                    
                    if point_count > 0:
                        success = True
                    else:
                        print("No midpoints created. Trying next method...")
                        
                except Exception as e:
                    print(f"Error using FeatureToPoint: {e}")
                    print("Trying next method...")
            
            if method == "manual" and not success:
                print("Using manual method to calculate midpoints...")
                try:
                    # Create a new point feature class manually
                    out_path = os.path.dirname(output_fc)
                    out_name = os.path.basename(temp_midpoints)
                    
                    if arcpy.Exists(os.path.join(out_path, out_name)):
                        arcpy.Delete_management(os.path.join(out_path, out_name))
                    
                    arcpy.CreateFeatureclass_management(
                        out_path, 
                        out_name, 
                        "POINT", 
                        spatial_reference=spatial_ref
                    )
                    
                    # Add a field to link back to the original feature
                    arcpy.AddField_management(temp_midpoints, "ORIG_FID", "LONG")
                    
                    # Calculate midpoints manually
                    with arcpy.da.SearchCursor(input_fc, ["SHAPE@", "OID@"]) as search_cursor:
                        with arcpy.da.InsertCursor(temp_midpoints, ["SHAPE@", "ORIG_FID"]) as insert_cursor:
                            points_created = 0
                            
                            for i, (geometry, oid) in enumerate(search_cursor):
                                try:
                                    # Get the length of the line
                                    if geometry and geometry.length > 0:
                                        # Create a point at the middle of the line
                                        mid_measure = geometry.length / 2.0
                                        midpoint = geometry.positionAlongLine(mid_measure)
                                        
                                        # Insert the point
                                        insert_cursor.insertRow([midpoint, oid])
                                        points_created += 1
                                        
                                        # Print details about this point (for debugging)
                                        if i < 5:  # only print the first 5 for brevity
                                            print(f"Line {oid}: Length={geometry.length}, Midpoint created at measure {mid_measure}")
                                    else:
                                        print(f"Skipping line {oid}: Invalid geometry or zero length")
                                except Exception as e:
                                    print(f"Error processing line {oid}: {e}")
                    
                    # Check if any points were created
                    point_count = points_created
                    print(f"Created {point_count} midpoints manually.")
                    
                    if point_count > 0:
                        success = True
                    else:
                        print("Failed to create midpoints using all available methods.")
                        
                except Exception as e:
                    print(f"Error in manual midpoint creation: {e}")
        
        # If we couldn't create any midpoints with any method, exit
        if not success:
            print("❌ Could not create midpoints with any available method. Skipping.")
            return
        
        # Copy the temporary midpoints to the final output location with all attributes
        print(f"Copying midpoints to final output: {output_fc}")
        
        # Simple copy approach - avoids issues with join
        arcpy.CopyFeatures_management(temp_midpoints, output_fc)
        
        # Add fields for midpoint info
        add_field_if_not_exists(output_fc, "MidptOf", "TEXT", field_length=10)
        add_field_if_not_exists(output_fc, "LAT", "DOUBLE")
        add_field_if_not_exists(output_fc, "LON", "DOUBLE")
        
        # Try to update the MidpointOf field with street name and add lat/long
        try:
            # Look for potential street name fields
            street_fields = ["STNAME", "ST_NAME", "STREET_NA"]
            source_field = None
            
            # Find the first available street field
            for field in street_fields:
                if field in [f.name for f in arcpy.ListFields(output_fc)]:
                    source_field = field
                    break
            
            # Update street name and calculate lat/long
            fields_to_update = ["SHAPE@"]
            
            # Only add fields that exist
            if "MidptOf" in [f.name for f in arcpy.ListFields(output_fc)]:
                fields_to_update.append("MidptOf")
                
            if "LAT" in [f.name for f in arcpy.ListFields(output_fc)]:
                fields_to_update.append("LAT")
                
            if "LON" in [f.name for f in arcpy.ListFields(output_fc)]:
                fields_to_update.append("LON")
            
            # Add source field if it exists
            if source_field:
                fields_to_update.append(source_field)
            
            with arcpy.da.UpdateCursor(output_fc, fields_to_update) as cursor:
                row_count = 0
                for row in cursor:
                    point = row[0]  # SHAPE@ is always first
                    row_count += 1
                    
                    if point:
                        # Calculate lat/long
                        try:
                            # Get the point geometry
                            point_geometry = point.firstPoint
                            
                            # Check if the spatial reference is geographic (lat/long) or projected
                            desc = arcpy.Describe(output_fc)
                            if desc.spatialReference.type == "Geographic":
                                # Already in geographic coordinates
                                lat_index = fields_to_update.index("LAT") if "LAT" in fields_to_update else -1
                                lon_index = fields_to_update.index("LON") if "LON" in fields_to_update else -1
                                
                                if lat_index > 0:
                                    row[lat_index] = point_geometry.Y  # Latitude
                                if lon_index > 0:
                                    row[lon_index] = point_geometry.X  # Longitude
                            else:
                                # Need to project the point to get geographic coordinates
                                # Create a temporary point in the current spatial reference
                                point_geom = arcpy.PointGeometry(point_geometry, desc.spatialReference)
                                
                                # Project to WGS84 (standard lat/long)
                                wgs84 = arcpy.SpatialReference(4326)
                                projected_point = point_geom.projectAs(wgs84)
                                
                                # Extract the lat/long values
                                lat_index = fields_to_update.index("LAT") if "LAT" in fields_to_update else -1
                                lon_index = fields_to_update.index("LON") if "LON" in fields_to_update else -1
                                
                                if lat_index > 0:
                                    row[lat_index] = projected_point.firstPoint.Y  # Latitude
                                if lon_index > 0:
                                    row[lon_index] = projected_point.firstPoint.X  # Longitude
                                
                            # Print a few examples for verification
                            if row_count <= 5:
                                lat_val = row[lat_index] if lat_index > 0 else "N/A"
                                lon_val = row[lon_index] if lon_index > 0 else "N/A"
                                print(f"Point {row_count}: Lat={lat_val}, Long={lon_val}")
                        except Exception as e:
                            print(f"Error calculating lat/long: {e}")
                    
                    # Update street name if available
                    midpt_index = fields_to_update.index("MidptOf") if "MidptOf" in fields_to_update else -1
                    source_index = fields_to_update.index(source_field) if source_field and source_field in fields_to_update else -1
                    
                    if midpt_index > 0 and source_index > 0 and row[source_index]:
                        street_val = row[source_index]
                        # Truncate street name to fit in field
                        if len(f"Mid {street_val}") > 10:
                            row[midpt_index] = f"Mid {street_val[:6]}"
                        else:
                            row[midpt_index] = f"Mid {street_val}"
                    
                    cursor.updateRow(row)
            
            print(f"✅ Successfully updated attributes for {row_count} points")
            
        except Exception as e:
            print(f"Error updating fields: {e}")
        
        # Clean up temporary data
        try:
            if arcpy.Exists(temp_midpoints):
                arcpy.Delete_management(temp_midpoints)
        except:
            pass
        
        # Check if any features were created in the final output
        final_count = int(arcpy.GetCount_management(output_fc).getOutput(0))
        if final_count > 0:
            print(f"✅ Successfully created midpoint shapefile with {final_count} points: {output_fc}")
        else:
            print(f"⚠️ Warning: Midpoint shapefile was created but contains no points: {output_fc}")
                
    except Exception as e:
        print(f"❌ Error creating midpoint shapefile: {e}")
        import traceback
        traceback.print_exc()

# ---------------------------------------------------------------------
# Get table fields to copy to the output shapefiles
# ---------------------------------------------------------------------
def get_table_fields(table_name):
    """Get a list of field names from the table to copy to output shapefiles."""
    try:
        # List of fields to ignore (system fields, etc.)
        ignore_fields = ['OBJECTID', 'OID', 'FID', 'SHAPE', 'SHAPE_LENGTH', 'SHAPE_AREA', 'GLOBALID']
        
        # Get all fields from the table
        fields = []
        for field in arcpy.ListFields(table_name):
            if field.name.upper() not in [f.upper() for f in ignore_fields]:
                fields.append(field.name)
                
        print(f"\nFields from table that will be copied: {', '.join(fields)}")
        
        # Create a mapping for shapefile compatibility (field names <= 10 chars)
        field_mapping = create_field_mapping(fields)
        print("\nField mappings for shapefile compatibility:")
        for orig, short in field_mapping.items():
            if orig != short:
                print(f"  • {orig} -> {short}")
                
        return fields, field_mapping
    except Exception as e:
        print(f"❌ Error getting table fields: {e}")
        return [], {}

# ---------------------------------------------------------------------
# Helper function for output shapefile creation with table fields
# ---------------------------------------------------------------------
def create_output_shapefile_with_table_fields(input_fc, output_fc, oid_list, threshold_type, threshold_value, pci_diff_dict, table_name, street_section_mapping):
    """Create a new shapefile containing only the features with specified OIDs and copy fields from the table."""
    if not oid_list:
        return
        
    try:
        # Create a feature layer of the input shapefile
        temp_layer = "temp_selection_layer"
        oid_field = arcpy.Describe(input_fc).OIDFieldName
        
        # Create a query to select the features
        oids_str = ", ".join(map(str, oid_list))
        where_clause = f"{oid_field} IN ({oids_str})"
        
        # Delete output if it exists
        if arcpy.Exists(output_fc):
            arcpy.Delete_management(output_fc)
            
        # Debug: Print fields in the input feature class
        print(f"\nFields in input shapefile: {input_fc}")
        for field in arcpy.ListFields(input_fc):
            print(f"  - {field.name} ({field.type})")
        
        # Make feature layer and copy features
        arcpy.MakeFeatureLayer_management(input_fc, temp_layer, where_clause)
        arcpy.CopyFeatures_management(temp_layer, output_fc)
        
        # Debug: Print fields in the new output feature class
        print(f"\nFields in new output shapefile (before adding fields): {output_fc}")
        for field in arcpy.ListFields(output_fc):
            print(f"  - {field.name} ({field.type})")
        
        # Add fields for threshold information (truncated for shapefile compatibility)
        add_field_if_not_exists(output_fc, "ThreshType", "TEXT", field_length=10)
        add_field_if_not_exists(output_fc, "ThreshVal", "LONG")
        add_field_if_not_exists(output_fc, "PCIDiff", "LONG")
        add_field_if_not_exists(output_fc, "QC_Street", "TEXT", field_length=10)
        
        # Get table fields to add to the output with mapping for shapefile compatibility
        table_fields, field_mapping = get_table_fields(table_name)
        field_types = {}
        
        # Get field types from the table
        for field in arcpy.ListFields(table_name):
            if field.name in table_fields:
                field_types[field.name] = (field.type, field.length, field.precision, field.scale)
        
        # Add table fields to the output shapefile
        for field_name in table_fields:
            # Skip field if it already exists
            if field_name.upper() in get_existing_fields(output_fc):
                continue
                
            # Use the truncated field name for shapefiles
            truncated_name = field_mapping[field_name]
            
            # Skip if truncated name already exists
            if truncated_name.upper() in get_existing_fields(output_fc):
                continue
                
            field_type, length, precision, scale = field_types.get(field_name, ("TEXT", 100, 0, 0))
            
            # Map ArcGIS field types to AddField field types
            if field_type == "String":
                field_type = "TEXT"
            elif field_type == "Integer":
                field_type = "LONG"
            elif field_type == "SmallInteger":
                field_type = "SHORT"
            elif field_type == "Double" or field_type == "Float":
                field_type = "DOUBLE"
            elif field_type == "Date":
                field_type = "DATE"
                
            print(f"Adding field {truncated_name} with type {field_type}")
            try:
                if field_type == "TEXT":
                    arcpy.AddField_management(output_fc, truncated_name, field_type, field_length=min(length, 255))
                elif field_type in ["DOUBLE", "FLOAT"]:
                    arcpy.AddField_management(output_fc, truncated_name, field_type, field_precision=precision, field_scale=scale)
                else:
                    arcpy.AddField_management(output_fc, truncated_name, field_type)
            except Exception as add_field_error:
                print(f"Error adding field {truncated_name}: {add_field_error}")
        
        # Debug: Print fields in the output after adding new fields
        print(f"\nFields in output shapefile (after adding fields): {output_fc}")
        for field in arcpy.ListFields(output_fc):
            print(f"  - {field.name} ({field.type})")
        
        # Build a dictionary of table records keyed by Street_ID and Section_ID
        table_records = {}
        try:
            # Get all fields from the table to copy
            table_cursor_fields = ["Street_ID", "Section_ID"] + table_fields
            
            # Get unique field names that exist in the table
            existing_table_fields = [field.name for field in arcpy.ListFields(table_name)]
            table_cursor_fields = [field for field in table_cursor_fields if field in existing_table_fields]
            
            print(f"Reading table with fields: {table_cursor_fields}")
            
            with arcpy.da.SearchCursor(table_name, table_cursor_fields) as cursor:
                for row in cursor:
                    street_id = row[0]
                    section_id = row[1]
                    key = f"{street_id} - {section_id}"
                    
                    # Store the rest of the fields
                    field_values = {}
                    for i, field_name in enumerate(table_cursor_fields[2:], 2):
                        field_values[field_name] = row[i]
                    
                    table_records[key] = field_values
        except Exception as table_read_error:
            print(f"Error reading table: {table_read_error}")
        
        # Update the output shapefile with threshold values first
        try:
            # Get field names that actually exist
            threshold_fields = get_safe_field_names(output_fc, ["ThreshType", "ThreshVal", "PCIDiff", "QC_Street", "StreetSec"])
            
            print(f"Updating threshold fields: {threshold_fields}")
            
            with arcpy.da.UpdateCursor(output_fc, threshold_fields) as cursor:
                for row in cursor:
                    # Find the PCI difference for this feature
                    fid = row[0]  # FID is always first
                    
                    pci_info = pci_diff_dict.get(fid, (None, None))
                    pci_diff = pci_info[0]
                    street_name = pci_info[1]
                    
                    # Update fields that exist (skip FID at index 0)
                    idx = 1
                    if "ThreshType" in threshold_fields[1:]:
                        row[idx] = threshold_type
                        idx += 1
                        
                    if "ThreshVal" in threshold_fields[1:]:
                        row[idx] = threshold_value
                        idx += 1
                        
                    if "PCIDiff" in threshold_fields[1:]:
                        # Handle NULL values correctly
                        if isinstance(pci_diff, (int, float)):
                            row[idx] = pci_diff
                        else:
                            row[idx] = 0  # Default value for non-nullable field
                        idx += 1
                        
                    if "QC_Street" in threshold_fields[1:] and street_name:
                        # Truncate street name if needed
                        row[idx] = street_name[:10] if len(street_name) > 10 else street_name
                        idx += 1
                        
                    # Get the StreetSec value if it exists
                    if "StreetSec" in threshold_fields[1:]:
                        street_sec = row[idx]
                        
                        # Store mapping for later use
                        if street_sec:
                            street_section_mapping[fid] = street_sec
                    
                    cursor.updateRow(row)
        except Exception as e:
            print(f"Error updating threshold fields: {e}")
            import traceback
            traceback.print_exc()
            
        # Now update the output shapefile with table data
        try:
            # Get output fields (using truncated field names for shapefile compatibility)
            output_fields = [field.name for field in arcpy.ListFields(output_fc)]
            
            # Get table fields that actually exist in the output
            update_fields = ["FID", "StreetSec"]
            
            # Add truncated field names that exist
            for field in table_fields:
                truncated = field_mapping[field]
                if truncated in output_fields:
                    update_fields.append(truncated)
            
            print(f"Update fields for table data: {update_fields}")
            
            with arcpy.da.UpdateCursor(output_fc, update_fields) as cursor:
                for row in cursor:
                    fid = row[0]
                    streetsec = row[1] if len(row) > 1 else None
                    
                    # If we don't have StreetSec directly, try to get it from the mapping
                    if not streetsec and fid in street_section_mapping:
                        streetsec = street_section_mapping[fid]
                    
                    # If we have a street section ID, try to find the matching table record
                    if streetsec and streetsec in table_records:
                        record = table_records[streetsec]
                        
                        # Handle NULL values for critical fields and update
                        for i, field_name in enumerate(update_fields[2:], 2):
                            # Find the original field name for this truncated name
                            orig_field = None
                            for original, truncated in field_mapping.items():
                                if truncated == field_name:
                                    orig_field = original
                                    break
                            
                            if not orig_field:
                                continue
                                
                            # Get the value from the table record
                            if orig_field in record:
                                value = record[orig_field]
                                
                                # Handle NULL values for non-nullable fields
                                if value is None:
                                    # Get field type to set appropriate default
                                    field_info = None
                                    for field in arcpy.ListFields(output_fc):
                                        if field.name == field_name:
                                            field_info = field
                                            break
                                            
                                    if field_info:
                                        if field_info.type in ["Integer", "SmallInteger", "Double", "Float", "LONG", "SHORT", "DOUBLE", "FLOAT"]:
                                            value = 0
                                        elif field_info.type in ["String", "TEXT"]:
                                            value = ""
                                        elif field_info.type in ["Date", "DATE"]:
                                            value = None  # Dates can be NULL in most formats
                                            
                                row[i] = value
                    
                    cursor.updateRow(row)
                    
            print(f"✅ Successfully created and updated {output_fc} with table fields")
                
        except Exception as e:
            print(f"❌ Error updating output shapefile with table fields: {e}")
            import traceback
            traceback.print_exc()
    finally:
        # Clean up
        if arcpy.Exists(temp_layer):
            arcpy.Delete_management(temp_layer)

# ---------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------
def analyze_pci_differences(shapefile_fc, table_name, lower_thresh, higher_thresh, 
                           lower_output_fc, higher_output_fc, combined_output_fc,
                           lower_midpoints_fc, higher_midpoints_fc, combined_midpoints_fc):
    """Match shapefile records to table rows and report PCI differences."""
    print("\nAnalyzing PCI differences for matched records...")

    try:
        # --- build a lookup dict from the table ---
        table_dict = {}   # { "StreetID - SectionID": [(last_pci, prev_pci, OID), …] }

        with arcpy.da.SearchCursor(
            table_name,
            ["Street_ID", "Section_ID", "Last_Insp_PCI", "Prev_Insp_PCI", "OBJECTID", "Street_Name"]
        ) as tbl_cur:
            for street_id, section_id, last_pci, prev_pci, tbl_oid, street_name in tbl_cur:
                key = f"{street_id} - {section_id}"
                table_dict.setdefault(key, []).append((last_pci, prev_pci, tbl_oid, street_name))

        # --- compare with the shapefile / feature class ---
        all_results = []
        lower_flagged = []
        higher_flagged = []
        lower_oids = []
        higher_oids = []
        all_flagged_oids = []
        pci_diff_dict = {}  # Dictionary to store PCI differences by feature ID
        street_section_mapping = {}  # Dictionary to store street section ID by feature ID

        with arcpy.da.SearchCursor(shapefile_fc, ["StreetSec", "FID"]) as shp_cur:
            for streetsec, shp_oid in shp_cur:
                # Store the street section ID for this feature
                street_section_mapping[shp_oid] = streetsec
                
                if streetsec in table_dict:
                    for last_pci, prev_pci, tbl_oid, street_name in table_dict[streetsec]:
                        # Handle NULL values properly
                        if last_pci is not None and prev_pci is not None:
                            pci_diff = last_pci - prev_pci
                            pci_diff_text = pci_diff
                            # Truncate street name for shapefile compatibility
                            street_name_short = street_name[:10] if len(street_name) > 10 else street_name
                            pci_diff_dict[shp_oid] = (pci_diff, street_name_short)
                            
                            # Check thresholds
                            if pci_diff <= lower_thresh:
                                flag = "⚠️ BELOW LOWER THRESHOLD"
                                lower_flagged.append((streetsec, street_name, pci_diff))
                                lower_oids.append(shp_oid)
                                all_flagged_oids.append(shp_oid)
                            elif pci_diff >= higher_thresh:
                                flag = "⚠️ ABOVE HIGHER THRESHOLD"
                                higher_flagged.append((streetsec, street_name, pci_diff))
                                higher_oids.append(shp_oid)
                                all_flagged_oids.append(shp_oid)
                            else:
                                flag = "OK"
                        else:
                            pci_diff_text = "N/A (missing PCI values)"
                            flag = "❓ MISSING DATA"

                        all_results.append(
                            {
                                "Shapefile_OID": shp_oid,
                                "Table_OID": tbl_oid,
                                "StreetSec": streetsec,
                                "Street_Name": street_name,
                                "Last_Insp_PCI": last_pci if last_pci is not None else "None",
                                "Prev_Insp_PCI": prev_pci if prev_pci is not None else "None",
                                "PCI_Difference": pci_diff_text,
                                "Flag": flag
                            }
                        )

        # --- print the findings ---
        print(f"\nPCI DIFFERENCES FOR MATCHED RECORDS "
              f"({len(all_results)} total)\n" + "-"*50)

        for r in all_results:
            print(
                f"Shp OID {r['Shapefile_OID']}  |  Tbl OID {r['Table_OID']}  |  Status: {r['Flag']}\n"
                f"StreetSec:       {r['StreetSec']}\n"
                f"Street Name:     {r['Street_Name']}\n"
                f"Last Insp PCI:   {r['Last_Insp_PCI']}\n"
                f"Prev Insp PCI:   {r['Prev_Insp_PCI']}\n"
                f"PCI Difference:  {r['PCI_Difference']}\n"
                + "-"*50
            )
        
        # --- print summary of flagged records ---
        print("\n" + "="*80)
        print(f"SUMMARY OF FLAGGED RECORDS:")
        print("="*80)
        
        if lower_flagged:
            print(f"\n🔻 RECORDS BELOW LOWER THRESHOLD ({lower_thresh}) - Total: {len(lower_flagged)}")
            print("-"*60)
            for streetsec, street_name, diff in sorted(lower_flagged, key=lambda x: x[2]):
                print(f"  • {street_name} ({streetsec}): PCI Difference = {diff}")
        else:
            print(f"\n✅ No records below the lower threshold of {lower_thresh}")
            
        if higher_flagged:
            print(f"\n🔺 RECORDS ABOVE HIGHER THRESHOLD ({higher_thresh}) - Total: {len(higher_flagged)}")
            print("-"*60)
            for streetsec, street_name, diff in sorted(higher_flagged, key=lambda x: x[2], reverse=True):
                print(f"  • {street_name} ({streetsec}): PCI Difference = {diff}")
        else:
            print(f"\n✅ No records above the higher threshold of {higher_thresh}")
            
        # --- create output shapefiles for flagged records ---
        # Create individual shapefiles for below and above thresholds
        if lower_oids:
            create_output_shapefile_with_table_fields(shapefile_fc, lower_output_fc, lower_oids, "below", lower_thresh, pci_diff_dict, table_name, street_section_mapping)
            print(f"\n✅ Created shapefile for records below threshold: {lower_output_fc}")
            
        if higher_oids:
            create_output_shapefile_with_table_fields(shapefile_fc, higher_output_fc, higher_oids, "above", higher_thresh, pci_diff_dict, table_name, street_section_mapping)
            print(f"\n✅ Created shapefile for records above threshold: {higher_output_fc}")
            
        # Create combined shapefile with all flagged records
        if all_flagged_oids:
            # Create a temporary feature layer
            temp_layer = "temp_all_flagged"
            oid_field = arcpy.Describe(shapefile_fc).OIDFieldName
            oids_str = ", ".join(map(str, all_flagged_oids))
            where_clause = f"{oid_field} IN ({oids_str})"
            
            if arcpy.Exists(combined_output_fc):
                arcpy.Delete_management(combined_output_fc)
                
            try:
                # Create and copy the features
                arcpy.MakeFeatureLayer_management(shapefile_fc, temp_layer, where_clause)
                arcpy.CopyFeatures_management(temp_layer, combined_output_fc)
                
                # Get table fields to add with mapping for shapefile compatibility
                table_fields, field_mapping = get_table_fields(table_name)
                
                # Add fields for threshold information (truncated for shapefile compatibility)
                add_field_if_not_exists(combined_output_fc, "ThreshType", "TEXT", field_length=10)
                add_field_if_not_exists(combined_output_fc, "PCIDiff", "LONG")
                add_field_if_not_exists(combined_output_fc, "QC_Street", "TEXT", field_length=10)
                
                # Add table fields to the output shapefile (truncated for shapefile compatibility)
                for field_name in table_fields:
                    # Skip field if it already exists
                    if field_name.upper() in get_existing_fields(combined_output_fc):
                        continue
                        
                    # Use the truncated field name for shapefiles
                    truncated_name = field_mapping[field_name]
                    
                    # Skip if truncated name already exists
                    if truncated_name.upper() in get_existing_fields(combined_output_fc):
                        continue
                        
                    field_type_info = None
                    for field in arcpy.ListFields(table_name):
                        if field.name == field_name:
                            field_type_info = (field.type, field.length, field.precision, field.scale)
                            break
                            
                    if not field_type_info:
                        field_type_info = ("TEXT", 100, 0, 0)
                        
                    field_type, length, precision, scale = field_type_info
                    
                    # Map ArcGIS field types to AddField field types
                    if field_type == "String":
                        field_type = "TEXT"
                    elif field_type == "Integer":
                        field_type = "LONG"
                    elif field_type == "SmallInteger":
                        field_type = "SHORT"
                    elif field_type == "Double" or field_type == "Float":
                        field_type = "DOUBLE"
                    elif field_type == "Date":
                        field_type = "DATE"
                        
                    print(f"Adding field {truncated_name} with type {field_type}")
                    try:
                        if field_type == "TEXT":
                            arcpy.AddField_management(combined_output_fc, truncated_name, field_type, field_length=min(length, 255))
                        elif field_type in ["DOUBLE", "FLOAT"]:
                            arcpy.AddField_management(combined_output_fc, truncated_name, field_type, field_precision=precision, field_scale=scale)
                        else:
                            arcpy.AddField_management(combined_output_fc, truncated_name, field_type)
                    except Exception as add_field_error:
                        print(f"Error adding field {truncated_name}: {add_field_error}")
                
                # Get a dictionary of table records keyed by Street_ID and Section_ID
                table_records = {}
                try:
                    # Get all fields from the table to copy
                    table_cursor_fields = ["Street_ID", "Section_ID"] + table_fields
                    
                    # Get unique field names that exist in the table
                    existing_table_fields = [field.name for field in arcpy.ListFields(table_name)]
                    table_cursor_fields = [field for field in table_cursor_fields if field in existing_table_fields]
                    
                    print(f"Reading table with fields: {table_cursor_fields}")
                    
                    with arcpy.da.SearchCursor(table_name, table_cursor_fields) as cursor:
                        for row in cursor:
                            street_id = row[0]
                            section_id = row[1]
                            key = f"{street_id} - {section_id}"
                            
                            # Store the rest of the fields
                            field_values = {}
                            for i, field_name in enumerate(table_cursor_fields[2:], 2):
                                field_values[field_name] = row[i]
                            
                            table_records[key] = field_values
                except Exception as table_read_error:
                    print(f"Error reading table: {table_read_error}")
                
                # Update threshold fields for the combined output
                try:
                    # Get field names that actually exist
                    threshold_fields = get_safe_field_names(combined_output_fc, ["ThreshType", "PCIDiff", "QC_Street", "StreetSec"])
                    
                    print(f"Updating threshold fields: {threshold_fields}")
                    
                    with arcpy.da.UpdateCursor(combined_output_fc, threshold_fields) as cursor:
                        for row in cursor:
                            fid = row[0]  # FID is always first
                            
                            pci_info = pci_diff_dict.get(fid, (None, None))
                            pci_diff = pci_info[0]
                            street_name = pci_info[1]
                            
                            # Update fields that exist (skip FID at index 0)
                            idx = 1
                            if "ThreshType" in threshold_fields[1:]:
                                if fid in lower_oids:
                                    row[idx] = f"Below {lower_thresh}"[:10]  # Truncate if needed
                                elif fid in higher_oids:
                                    row[idx] = f"Above {higher_thresh}"[:10]  # Truncate if needed
                                idx += 1
                                
                            if "PCIDiff" in threshold_fields[1:]:
                                # Handle NULL values for non-nullable fields
                                if isinstance(pci_diff, (int, float)):
                                    row[idx] = pci_diff
                                else:
                                    row[idx] = 0  # Default for non-nullable field
                                idx += 1
                                
                            if "QC_Street" in threshold_fields[1:] and street_name:
                                # Truncate street name if needed
                                row[idx] = street_name[:10]
                                idx += 1
                                
                            # Get the StreetSec value if it exists
                            if "StreetSec" in threshold_fields[1:]:
                                street_sec = row[idx]
                                
                                # Store mapping for later use
                                if street_sec:
                                    street_section_mapping[fid] = street_sec
                            
                            cursor.updateRow(row)
                            
                    # Update the table fields in combined output
                    # Get output fields (using truncated field names for shapefile compatibility)
                    output_fields = [field.name for field in arcpy.ListFields(combined_output_fc)]
                    
                    # Get table fields that actually exist in the output
                    update_fields = ["FID", "StreetSec"]
                    
                    # Add truncated field names that exist
                    for field in table_fields:
                        truncated = field_mapping[field]
                        if truncated in output_fields:
                            update_fields.append(truncated)
                    
                    print(f"Update fields for table data: {update_fields}")
                    
                    with arcpy.da.UpdateCursor(combined_output_fc, update_fields) as cursor:
                        for row in cursor:
                            fid = row[0]
                            streetsec = row[1] if len(row) > 1 else None
                            
                            # If we don't have StreetSec directly, try to get it from the mapping
                            if not streetsec and fid in street_section_mapping:
                                streetsec = street_section_mapping[fid]
                            
                            # If we have a street section ID, try to find the matching table record
                            if streetsec and streetsec in table_records:
                                record = table_records[streetsec]
                                
                                # Handle NULL values for non-nullable fields and update
                                for i, field_name in enumerate(update_fields[2:], 2):
                                    # Find the original field name for this truncated name
                                    orig_field = None
                                    for original, truncated in field_mapping.items():
                                        if truncated == field_name:
                                            orig_field = original
                                            break
                                    
                                    if not orig_field:
                                        continue
                                        
                                    # Get the value from the table record
                                    if orig_field in record:
                                        value = record[orig_field]
                                        
                                        # Handle NULL values for non-nullable fields
                                        if value is None:
                                            # Get field type to set appropriate default
                                            field_info = None
                                            for field in arcpy.ListFields(combined_output_fc):
                                                if field.name == field_name:
                                                    field_info = field
                                                    break
                                                    
                                            if field_info:
                                                if field_info.type in ["Integer", "SmallInteger", "Double", "Float", "LONG", "SHORT", "DOUBLE", "FLOAT"]:
                                                    value = 0
                                                elif field_info.type in ["String", "TEXT"]:
                                                    value = ""
                                                elif field_info.type in ["Date", "DATE"]:
                                                    value = None  # Dates can be NULL in most formats
                                                    
                                        row[i] = value
                            
                            cursor.updateRow(row)
                        
                    print(f"\n✅ Created combined shapefile with all flagged records and table fields: {combined_output_fc}")
                except Exception as e:
                    print(f"❌ Error updating combined output shapefile: {e}")
                    import traceback
                    traceback.print_exc()
            except Exception as e:
                print(f"❌ Error creating combined output shapefile: {e}")
                import traceback
                traceback.print_exc()
            finally:
                if arcpy.Exists(temp_layer):
                    arcpy.Delete_management(temp_layer)
        
        # --- Create midpoint shapefiles ---
        # Create midpoints for individual and combined output shapefiles
        if arcpy.Exists(lower_output_fc):
            create_midpoint_shapefile(lower_output_fc, lower_midpoints_fc)
            
        if arcpy.Exists(higher_output_fc):
            create_midpoint_shapefile(higher_output_fc, higher_midpoints_fc)
            
        if arcpy.Exists(combined_output_fc):
            create_midpoint_shapefile(combined_output_fc, combined_midpoints_fc)

    except Exception as e:
        print(f"❌ Error during processing: {e}")
        print(f"❌ Currently using:\n  • Shapefile: {shapefile_fc}\n  • Table: {table_name}")
        import traceback
        traceback.print_exc()
        
        # Print field names to help with debugging
        try:
            fields = arcpy.ListFields(table_name)
            print("\n❌ Available fields in the table:")
            for field in fields:
                print(f"  - {field.name} ({field.type})")
                
            fields = arcpy.ListFields(shapefile_fc)
            print("\n❌ Available fields in the shapefile:")
            for field in fields:
                print(f"  - {field.name} ({field.type})")
        except Exception as field_error:
            print(f"  Cannot list fields: {field_error}")

# ---------------------------------------------------------------------
# Run it
# ---------------------------------------------------------------------
try:
    analyze_pci_differences(shapefile, table, lower_threshold, higher_threshold, 
                           lower_output, higher_output, combined_output,
                           lower_midpoints, higher_midpoints, combined_midpoints)
    print("\nScript completed!")
except Exception as outer_error:
    print(f"\n❌ Fatal error: {outer_error}")
    import traceback
    traceback.print_exc()
    print(f"❌ Currently using:\n  • Shapefile: {shapefile}\n  • Table: {table}")
