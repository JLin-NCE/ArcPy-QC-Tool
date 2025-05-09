import arcpy
import os
import math
import datetime
import uuid

def find_midpoints_with_pci_matching():
    """
    1. Ask user for threshold values
    2. Find midpoints of each line in WildomarPMPJordan feature layer
    3. Match these midpoints with records from PCI Differences table
    4. Calculate difference between Prev_Insp_PCI and Last_Insp_PCI
    5. Filter results based on threshold values
    6. Create one shapefile and one table with the specified columns
    """
    try:
        # Ask user for threshold values
        print("====== PCI Difference Threshold Input ======")
        lower_threshold = float(input("Enter LOWER threshold value (include points with PCI difference <= this value): "))
        higher_threshold = float(input("Enter HIGHER threshold value (include points with PCI difference >= this value): "))
        print(f"Will include points with PCI difference <= {lower_threshold} OR >= {higher_threshold}")
        print("============================================")
        
        print("\nStarting to access and match data...")
        
        # Get the current project
        aprx = arcpy.mp.ArcGISProject("CURRENT")
        print(f"Current project: {aprx.filePath}")
        
        # Get the active map and find the WildomarPMPJordan feature layer
        wildomar_fc_path = None
        active_map = None
        
        # Search for the feature class in all maps
        for m in aprx.listMaps():
            for lyr in m.listLayers():
                if lyr.isFeatureLayer and "WildomarPMPJordan" in lyr.name:
                    wildomar_fc_path = lyr.dataSource
                    wildomar_layer = lyr
                    active_map = m
                    print(f"Found layer: {lyr.name} in map: {m.name}")
                    break
            if wildomar_fc_path:
                break
        
        if not wildomar_fc_path:
            print("ERROR: WildomarPMPJordan feature class not found in the project.")
            return
        
        # Define WGS84 (lat/long) spatial reference for external API URLs
        wgs84 = arcpy.SpatialReference(4326)  # EPSG code for WGS84
        
        # Get the spatial reference of the feature layer
        desc = arcpy.Describe(wildomar_layer)
        layer_sr = desc.spatialReference
        
        print(f"Feature layer spatial reference: {layer_sr.name} ({layer_sr.factoryCode})")
        print(f"Target spatial reference: WGS84 (4326)")
        
        # Find the PCI Differences table
        pci_table = None
        for table in active_map.listTables():
            if "PCI Differences" in table.name:
                pci_table = table
                print(f"Found standalone table: {table.name}")
                break
        
        if not pci_table:
            print("WARNING: PCI Differences table not found in the active map.")
            return
        
        # Determine field names in the feature layer
        print("\nLooking for key fields in the feature layer...")
        shapefile_fields = arcpy.ListFields(wildomar_layer)
        
        # Try to find the StreetSec field or StreetID/SectionID fields and Street Name
        street_sec_field = None
        street_id_field = None
        section_id_field = None
        street_name_field = None
        begin_loc_field = None
        end_loc_field = None
        
        for field in shapefile_fields:
            field_name = field.name
            
            # Look for combined field
            if "STREETSEC" in field_name.upper() or field_name.upper() == "STREET_SEC":
                street_sec_field = field_name
                print(f"Found combined street/section field: {field_name}")
            
            # Look for separate ID fields
            if "STREET" in field_name.upper() and "ID" in field_name.upper():
                street_id_field = field_name
                print(f"Found street ID field: {field_name}")
            if "SECTION" in field_name.upper() and "ID" in field_name.upper():
                section_id_field = field_name
                print(f"Found section ID field: {field_name}")
                
            # Look for street name field
            if "STREET" in field_name.upper() and "NAME" in field_name.upper():
                street_name_field = field_name
                print(f"Found street name field: {field_name}")
                
            # Look for begin/end location fields
            if "BEGIN" in field_name.upper() and "LOC" in field_name.upper():
                begin_loc_field = field_name
                print(f"Found begin location field in feature layer: {field_name}")
            if "END" in field_name.upper() and "LOC" in field_name.upper():
                end_loc_field = field_name
                print(f"Found end location field in feature layer: {field_name}")
        
        # Determine field names in the PCI table
        print("\nLooking for key fields in the PCI Differences table...")
        pci_fields = arcpy.ListFields(pci_table)
        
        pci_street_id_field = None
        pci_section_id_field = None
        prev_insp_pci_field = None
        last_insp_pci_field = None
        prev_insp_date_field = None
        m_r_date_field = None
        m_r_treatment_field = None
        last_insp_date_field = None
        begin_loc_field_pci = None  # NEW: Look for begin location in PCI table
        end_loc_field_pci = None    # NEW: Look for end location in PCI table
        
        for field in pci_fields:
            field_name = field.name
            
            if "STREET" in field_name.upper() and "ID" in field_name.upper():
                pci_street_id_field = field_name
                print(f"Found street ID field: {field_name}")
            if "SECTION" in field_name.upper() and "ID" in field_name.upper():
                pci_section_id_field = field_name
                print(f"Found section ID field: {field_name}")
            
            # Look for PCI fields in the table
            if "PREV" in field_name.upper() and "PCI" in field_name.upper():
                prev_insp_pci_field = field_name
                print(f"Found previous inspection PCI field: {field_name}")
            if "LAST" in field_name.upper() and "PCI" in field_name.upper():
                last_insp_pci_field = field_name
                print(f"Found last inspection PCI field: {field_name}")
                
            # Look for date fields
            if "PREV" in field_name.upper() and "DATE" in field_name.upper():
                prev_insp_date_field = field_name
                print(f"Found previous inspection date field: {field_name}")
            if "M&R" in field_name.upper() and "DATE" in field_name.upper():
                m_r_date_field = field_name
                print(f"Found M&R date field: {field_name}")
            if "LAST" in field_name.upper() and "DATE" in field_name.upper():
                last_insp_date_field = field_name
                print(f"Found last inspection date field: {field_name}")
                
            # Look for M&R treatment field
            if "TREATMENT" in field_name.upper() or "M&R" in field_name.upper() and "NAME" in field_name.upper():
                m_r_treatment_field = field_name
                print(f"Found M&R treatment field: {field_name}")
                
            # NEW: Look for begin/end location fields in the PCI table
            if "BEGIN" in field_name.upper() and "LOC" in field_name.upper():
                begin_loc_field_pci = field_name
                print(f"Found begin location field in PCI table: {field_name}")
            if "END" in field_name.upper() and "LOC" in field_name.upper():
                end_loc_field_pci = field_name
                print(f"Found end location field in PCI table: {field_name}")
        
        # Check if we have the necessary fields
        if not pci_street_id_field or not pci_section_id_field:
            print("ERROR: Could not find Street ID and Section ID fields in the PCI table.")
            return
        
        if not street_sec_field and (not street_id_field or not section_id_field):
            print("ERROR: Could not find StreetSec or Street ID/Section ID fields in the feature layer.")
            return
        
        # Check if PCI fields were found in the table
        if not prev_insp_pci_field or not last_insp_pci_field:
            print("ERROR: Could not find Prev_Insp_PCI or Last_Insp_PCI fields in the PCI table.")
            return
        else:
            print(f"Found both PCI fields in the table. Will calculate difference: {prev_insp_pci_field} - {last_insp_pci_field}")
        
        # Create a dictionary to store PCI data for quicker lookups
        print("\nReading PCI Differences data...")
        pci_data = {}
        
        # Determine which fields to fetch from the PCI table
        pci_fields_to_fetch = [pci_street_id_field, pci_section_id_field]
        
        # Add required fields if they exist
        if prev_insp_pci_field:
            pci_fields_to_fetch.append(prev_insp_pci_field)
        if last_insp_pci_field:
            pci_fields_to_fetch.append(last_insp_pci_field)
        if prev_insp_date_field:
            pci_fields_to_fetch.append(prev_insp_date_field)
        if m_r_date_field:
            pci_fields_to_fetch.append(m_r_date_field)
        if m_r_treatment_field:
            pci_fields_to_fetch.append(m_r_treatment_field)
        if last_insp_date_field:
            pci_fields_to_fetch.append(last_insp_date_field)
        # NEW: Add begin/end location fields from PCI table if they exist
        if begin_loc_field_pci:
            pci_fields_to_fetch.append(begin_loc_field_pci)
        if end_loc_field_pci:
            pci_fields_to_fetch.append(end_loc_field_pci)
        
        with arcpy.da.SearchCursor(pci_table, pci_fields_to_fetch) as cursor:
            for row in cursor:
                street_id = str(row[0]).strip()
                section_id = str(row[1]).strip()
                
                # Create key in "Street_ID - Section_ID" format
                key = f"{street_id} - {section_id}"
                
                record_data = {
                    'street_id': street_id,
                    'section_id': section_id
                }
                
                # Get field index
                field_idx = 2
                
                # Get PCI values if fields are available
                if prev_insp_pci_field:
                    record_data['prev_pci'] = row[field_idx]
                    field_idx += 1
                if last_insp_pci_field:
                    record_data['last_pci'] = row[field_idx]
                    field_idx += 1
                
                # Get date and treatment fields
                if prev_insp_date_field:
                    record_data['prev_insp_date'] = row[field_idx]
                    field_idx += 1
                if m_r_date_field:
                    record_data['m_r_date'] = row[field_idx]
                    field_idx += 1
                if m_r_treatment_field:
                    record_data['m_r_treatment'] = row[field_idx]
                    field_idx += 1
                if last_insp_date_field:
                    record_data['last_insp_date'] = row[field_idx]
                    field_idx += 1
                
                # NEW: Get begin/end location fields from PCI table if they exist
                if begin_loc_field_pci:
                    record_data['begin_loc_pci'] = row[field_idx]
                    field_idx += 1
                if end_loc_field_pci:
                    record_data['end_loc_pci'] = row[field_idx]
                    field_idx += 1
                
                # Calculate PCI difference if both PCI fields are available
                if 'prev_pci' in record_data and 'last_pci' in record_data:
                    prev_pci = record_data['prev_pci']
                    last_pci = record_data['last_pci']
                    
                    # Check for valid numeric values before calculating
                    if prev_pci is not None and last_pci is not None:
                        try:
                            pci_diff_calc = float(prev_pci) - float(last_pci)
                            record_data['pci_diff_calc'] = pci_diff_calc
                            
                            # Check if the difference meets the threshold criteria
                            if pci_diff_calc <= lower_threshold or pci_diff_calc >= higher_threshold:
                                # Store all the collected data only if it meets threshold criteria
                                pci_data[key] = record_data
                                print(f"Record {key} included: PCI difference {pci_diff_calc} (Thresholds: <= {lower_threshold} or >= {higher_threshold})")
                            else:
                                print(f"Record {key} excluded: PCI difference {pci_diff_calc} not within thresholds")
                        except (ValueError, TypeError):
                            print(f"Warning: Could not calculate PCI difference for {key}. Values: {prev_pci}, {last_pci}")
        
        print(f"Loaded {len(pci_data)} records from PCI Differences table that meet threshold criteria.")
        
        # Outputs in default GDB
        default_gdb = aprx.defaultGeodatabase
        print(f"\nCreating outputs in default geodatabase: {default_gdb}")
        
        # Create more user-friendly names
        current_date = datetime.datetime.now().strftime("%Y%m%d")
        formatted_thresholds = f"PCI_Diff_LE_{lower_threshold}_GE_{higher_threshold}"
        
        # More recognizable names for outputs
        table_name = f"Wildomar_PCI_Threshold_Table_{current_date}"
        fc_name = f"Wildomar_PCI_Threshold_Points_{current_date}"
        
        table_path = os.path.join(default_gdb, table_name)
        fc_path = os.path.join(default_gdb, fc_name)
        
        # Cleanup ALL existing outputs with similar names to avoid duplicates
        print("\nPerforming thorough cleanup of existing layers and tables...")

        # 1. Remove ALL layers that contain our naming pattern
        layers_to_remove = []
        for lyr in active_map.listLayers():
            if "PCI_Threshold_Points" in lyr.name or "Midpoints" in lyr.name or "TEMP_Midpoints" in lyr.name:
                layers_to_remove.append(lyr)
                print(f"Will remove layer: {lyr.name}")

        # Remove the layers outside the loop to avoid modifying while iterating
        for lyr in layers_to_remove:
            try:
                active_map.removeLayer(lyr)
                print(f"Removed layer: {lyr.name}")
            except Exception as e:
                print(f"Warning: Could not remove layer {lyr.name}. Error: {str(e)}")

        # 2. Remove ALL tables that contain our naming pattern
        tables_to_remove = []
        for tbl in active_map.listTables():
            if "PCI_Threshold_Table" in tbl.name:
                tables_to_remove.append(tbl)
                print(f"Will remove table: {tbl.name}")

        # Remove the tables outside the loop
        for tbl in tables_to_remove:
            try:
                active_map.removeTable(tbl)
                print(f"Removed table: {tbl.name}")
            except Exception as e:
                print(f"Warning: Could not remove table {tbl.name}. Error: {str(e)}")

        # 3. Delete ALL feature classes and tables in the geodatabase with similar names
        fc_pattern = f"*PCI_Threshold_Points*"
        table_pattern = f"*PCI_Threshold_Table*"
        midpoints_pattern = f"*Midpoints*"

        # Get lists of items to delete
        arcpy_workspace = aprx.defaultGeodatabase
        arcpy.env.workspace = arcpy_workspace

        # Delete feature classes that match our patterns
        for fc in arcpy.ListFeatureClasses(fc_pattern):
            try:
                fc_path_to_delete = os.path.join(arcpy_workspace, fc)
                arcpy.management.Delete(fc_path_to_delete)
                print(f"Deleted existing feature class: {fc}")
            except Exception as e:
                print(f"Warning: Could not delete feature class {fc}. Error: {str(e)}")

        # Delete tables that match our patterns
        for tbl in arcpy.ListTables(table_pattern):
            try:
                tbl_path_to_delete = os.path.join(arcpy_workspace, tbl)
                arcpy.management.Delete(tbl_path_to_delete)
                print(f"Deleted existing table: {tbl}")
            except Exception as e:
                print(f"Warning: Could not delete table {tbl}. Error: {str(e)}")

        # Delete any temporary midpoints feature classes
        for temp_fc in arcpy.ListFeatureClasses(midpoints_pattern):
            try:
                temp_fc_path = os.path.join(arcpy_workspace, temp_fc)
                arcpy.management.Delete(temp_fc_path)
                print(f"Deleted temporary feature class: {temp_fc}")
            except Exception as e:
                print(f"Warning: Could not delete temporary feature class {temp_fc}. Error: {str(e)}")
            
        # Create a unique name for the temporary midpoints
        unique_id = str(uuid.uuid4())[:8]
        midpoints_fc_name = f"TEMP_Midpoints_{unique_id}"
        midpoints_fc_path = os.path.join(default_gdb, midpoints_fc_name)
        
        # Create midpoints using the FeatureToPoint tool
        print("\nGenerating midpoints using FeatureToPoint tool...")
        if arcpy.Exists(midpoints_fc_path):
            arcpy.management.Delete(midpoints_fc_path)
            
        arcpy.management.FeatureToPoint(
            wildomar_fc_path, 
            midpoints_fc_path, 
            "CENTROID"  # Using CENTROID for lines will give the midpoint
        )
        
        print(f"Midpoints created successfully at: {midpoints_fc_path}")
        
        # Determine fields to retrieve from the original feature class
        shapefile_retrieve_fields = ["SHAPE@"]
        
        # If we have a combined field, use it
        if street_sec_field:
            shapefile_retrieve_fields.append(street_sec_field)
        # Otherwise use separate fields
        else:
            shapefile_retrieve_fields.append(street_id_field)
            shapefile_retrieve_fields.append(section_id_field)
            
        # Add additional fields if they exist
        if street_name_field:
            shapefile_retrieve_fields.append(street_name_field)
        if begin_loc_field:
            shapefile_retrieve_fields.append(begin_loc_field)
        if end_loc_field:
            shapefile_retrieve_fields.append(end_loc_field)
        
        # Join fields from original data with midpoint geometries
        # First, create a dictionary of attributes from the original feature class
        attributes_dict = {}
        
        with arcpy.da.SearchCursor(wildomar_layer, shapefile_retrieve_fields) as cursor:
            for i, row in enumerate(cursor):
                # Get the shape
                shape = row[0]  # SHAPE@
                
                # Initialize with defaults
                street_id_value = ""
                section_id_value = ""
                street_name_value = ""
                begin_loc_value = ""
                end_loc_value = ""
                
                field_idx = 1  # Start from field after SHAPE@
                
                # Determine the key based on available fields
                if street_sec_field:
                    street_sec_value = str(row[field_idx]).strip()
                    key = street_sec_value
                    street_id_value = street_sec_value
                    section_id_value = street_sec_value
                    field_idx += 1
                else:
                    street_id_value = str(row[field_idx]).strip()
                    section_id_value = str(row[field_idx + 1]).strip()
                    key = f"{street_id_value} - {section_id_value}"
                    field_idx += 2
                
                # Get additional fields if they exist
                if street_name_field:
                    street_name_value = row[field_idx]
                    field_idx += 1
                if begin_loc_field:
                    begin_loc_value = row[field_idx]
                    field_idx += 1
                if end_loc_field:
                    end_loc_value = row[field_idx]
                    field_idx += 1
                
                # Calculate midpoint
                midpoint = shape.positionAlongLine(0.5, True)
                
                # Project the point to WGS84 for API URLs
                proj = midpoint.projectAs(wgs84)
                lon = proj.firstPoint.X
                lat = proj.firstPoint.Y
                
                # Store original coordinates
                original_x = midpoint.firstPoint.X
                original_y = midpoint.firstPoint.Y
                
                # Store attributes
                attributes_dict[i] = {
                    'street_id': street_id_value,
                    'section_id': section_id_value,
                    'combined_key': key,
                    'street_name': street_name_value,
                    'begin_loc': begin_loc_value,
                    'end_loc': end_loc_value,
                    'latitude': lat,
                    'longitude': lon,
                    'original_x': original_x,
                    'original_y': original_y,
                    'spatial_reference': layer_sr
                }
        
        # Now match attributes with PCI data
        print("\nMatching attributes with PCI data...")
        results = []
        
        for fid, attrs in attributes_dict.items():
            key = attrs['combined_key']
            
            # Check if this record matches a PCI record that meets threshold criteria
            if key in pci_data:
                pci_record = pci_data[key]
                
                # Create a new combined record
                combined_record = {}
                
                # Copy all attributes from feature layer
                for k, v in attrs.items():
                    combined_record[k] = v
                
                # Copy all attributes from PCI table
                for k, v in pci_record.items():
                    combined_record[k] = v
                
                # NEW: Prioritize begin/end locations from PCI table if they exist
                if 'begin_loc_pci' in pci_record and pci_record['begin_loc_pci']:
                    combined_record['begin_loc'] = pci_record['begin_loc_pci']
                    print(f"Using begin location from PCI table for {key}")
                
                if 'end_loc_pci' in pci_record and pci_record['end_loc_pci']:
                    combined_record['end_loc'] = pci_record['end_loc_pci']
                    print(f"Using end location from PCI table for {key}")
                
                results.append(combined_record)
                print(f"Matched record: {key}")
        
        print(f"Found {len(results)} matching records that meet threshold criteria.")
        
        # Clean up the temporary midpoints feature - IMPORTANT!
        try:
            if arcpy.Exists(midpoints_fc_path):
                arcpy.management.Delete(midpoints_fc_path)
                print(f"Successfully deleted temporary midpoints: {midpoints_fc_name}")
        except Exception as e:
            print(f"WARNING: Failed to delete temporary midpoints: {midpoints_fc_name}. Error: {str(e)}")
        
        # 1. Create the table with specified columns
        print(f"Creating table: {table_name}")
        arcpy.management.CreateTable(default_gdb, table_name)
        arcpy.management.AddField(table_path, "StreetID", "TEXT", field_length=50)
        arcpy.management.AddField(table_path, "SectionID", "TEXT", field_length=50)
        arcpy.management.AddField(table_path, "StreetName", "TEXT", field_length=100)
        arcpy.management.AddField(table_path, "BeginLocation", "TEXT", field_length=100)
        arcpy.management.AddField(table_path, "EndLocation", "TEXT", field_length=100)
        arcpy.management.AddField(table_path, "PrevInspDate", "DATE")
        arcpy.management.AddField(table_path, "PrevInspPCI", "DOUBLE")
        arcpy.management.AddField(table_path, "MRDate", "DATE")
        arcpy.management.AddField(table_path, "MRTreatmentName", "TEXT", field_length=100)
        arcpy.management.AddField(table_path, "LastInspDate", "DATE")
        arcpy.management.AddField(table_path, "LastInspPCI", "DOUBLE")
        arcpy.management.AddField(table_path, "Lat", "DOUBLE")
        arcpy.management.AddField(table_path, "Long", "DOUBLE")
        arcpy.management.AddField(table_path, "MapillaryLink", "TEXT", field_length=255)
        arcpy.management.AddField(table_path, "GoogleImageLink", "TEXT", field_length=255)
        
        # Insert the data into the table
        print("Inserting data into the table...")
        with arcpy.da.InsertCursor(table_path, [
                "StreetID", "SectionID", "StreetName", "BeginLocation", "EndLocation",
                "PrevInspDate", "PrevInspPCI", "MRDate", "MRTreatmentName", 
                "LastInspDate", "LastInspPCI", "Lat", "Long", 
                "MapillaryLink", "GoogleImageLink"
            ]) as ic:
            for r in results:
                lat = r['latitude']
                lon = r['longitude']
                # Generate API URLs for external services
                map_url = f"https://www.mapillary.com/app/user/view?lat={lat}&lng={lon}&z=18"
                g_url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}"
                
                # Get values with defaults for missing fields
                street_id = r.get('street_id', "")
                section_id = r.get('section_id', "")
                street_name = r.get('street_name', "")
                begin_loc = r.get('begin_loc', "")
                end_loc = r.get('end_loc', "")
                prev_insp_date = r.get('prev_insp_date', None)
                prev_insp_pci = r.get('prev_pci', None)
                m_r_date = r.get('m_r_date', None)
                m_r_treatment = r.get('m_r_treatment', "")
                last_insp_date = r.get('last_insp_date', None)
                last_insp_pci = r.get('last_pci', None)
                
                # Debug output for begin and end locations
                print(f"Record {street_id}-{section_id}: BeginLoc={begin_loc}, EndLoc={end_loc}")
                
                ic.insertRow([
                    street_id, section_id, street_name, begin_loc, end_loc,
                    prev_insp_date, prev_insp_pci, m_r_date, m_r_treatment,
                    last_insp_date, last_insp_pci, lat, lon,
                    map_url, g_url
                ])
        
        # 2. Create one shapefile in WGS84 format
        print(f"\nCreating points feature class in WGS84: {fc_name}")
        arcpy.management.CreateFeatureclass(default_gdb, fc_name, "POINT", 
                                          spatial_reference=wgs84)
        
        # Add the same fields to the feature class
        arcpy.management.AddField(fc_path, "StreetID", "TEXT", field_length=50)
        arcpy.management.AddField(fc_path, "SectionID", "TEXT", field_length=50)
        arcpy.management.AddField(fc_path, "StreetName", "TEXT", field_length=100)
        arcpy.management.AddField(fc_path, "BeginLocation", "TEXT", field_length=100)
        arcpy.management.AddField(fc_path, "EndLocation", "TEXT", field_length=100)
        arcpy.management.AddField(fc_path, "PrevInspDate", "DATE")
        arcpy.management.AddField(fc_path, "PrevInspPCI", "DOUBLE")
        arcpy.management.AddField(fc_path, "MRDate", "DATE")
        arcpy.management.AddField(fc_path, "MRTreatmentName", "TEXT", field_length=100)
        arcpy.management.AddField(fc_path, "LastInspDate", "DATE")
        arcpy.management.AddField(fc_path, "LastInspPCI", "DOUBLE")
        arcpy.management.AddField(fc_path, "Lat", "DOUBLE")
        arcpy.management.AddField(fc_path, "Long", "DOUBLE")
        arcpy.management.AddField(fc_path, "MapillaryLink", "TEXT", field_length=255)
        arcpy.management.AddField(fc_path, "GoogleImageLink", "TEXT", field_length=255)
        
        # Populate the feature class
        print("Populating the WGS84 points feature class...")
        with arcpy.da.InsertCursor(fc_path, [
                "SHAPE@", "StreetID", "SectionID", "StreetName", "BeginLocation", "EndLocation",
                "PrevInspDate", "PrevInspPCI", "MRDate", "MRTreatmentName", 
                "LastInspDate", "LastInspPCI", "Lat", "Long", 
                "MapillaryLink", "GoogleImageLink"
            ]) as fic:
            for r in results:
                pt = arcpy.Point(r['longitude'], r['latitude'])
                pg = arcpy.PointGeometry(pt, wgs84)
                lat = r['latitude']
                lon = r['longitude']
                
                # Generate API URLs for external services
                map_url = f"https://www.mapillary.com/app/user/view?lat={lat}&lng={lon}&z=18"
                g_url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}"
                
                # Get values with defaults for missing fields
                street_id = r.get('street_id', "")
                section_id = r.get('section_id', "")
                street_name = r.get('street_name', "")
                begin_loc = r.get('begin_loc', "")
                end_loc = r.get('end_loc', "")
                prev_insp_date = r.get('prev_insp_date', None)
                prev_insp_pci = r.get('prev_pci', None)
                m_r_date = r.get('m_r_date', None)
                m_r_treatment = r.get('m_r_treatment', "")
                last_insp_date = r.get('last_insp_date', None)
                last_insp_pci = r.get('last_pci', None)
                
                # Debug output for begin and end locations in shapefile
                print(f"Adding to shapefile - {street_id}-{section_id}: BeginLoc={begin_loc}, EndLoc={end_loc}")
                
                fic.insertRow([
                    pg, street_id, section_id, street_name, begin_loc, end_loc,
                    prev_insp_date, prev_insp_pci, m_r_date, m_r_treatment,
                    last_insp_date, last_insp_pci, lat, lon,
                    map_url, g_url
                ])
        
        # Add the outputs to the map exactly once
        print("Adding the outputs to the map...")
        active_map.addDataFromPath(table_path)
        active_map.addDataFromPath(fc_path)
        
        # Find the newly added layers and apply styling
        added_layer = None
        for lyr in active_map.listLayers():
            if lyr.isFeatureLayer and lyr.dataSource == fc_path:
                added_layer = lyr
                symb = lyr.symbology
                if hasattr(symb, 'renderer'):
                    if hasattr(symb.renderer, 'symbol'):
                        symb.renderer.symbol.size = 8
                        symb.renderer.symbol.color = {'RGB': [255, 0, 0, 100]}
                        lyr.symbology = symb
                        print(f"Applied styling to layer: {lyr.name}")
                break
        
        # Save the project to preserve changes
        aprx.save()
        print("Project saved successfully with all changes.")
        print("\nScript completed successfully!")
        print(f"Created table: {table_name}")
        print(f"Created feature class: {fc_name}")
        print(f"Found {len(results)} points that met the threshold criteria.")

        # Summary report of Begin/End Location fields processing
        print("\n===== Begin/End Location Fields Summary =====")
        begin_loc_feature_found = "Yes" if begin_loc_field else "No"
        end_loc_feature_found = "Yes" if end_loc_field else "No"
        begin_loc_pci_found = "Yes" if begin_loc_field_pci else "No"
        end_loc_pci_found = "Yes" if end_loc_field_pci else "No"
        
        print(f"Begin Location field found in feature layer: {begin_loc_feature_found}")
        print(f"End Location field found in feature layer: {end_loc_feature_found}")
        print(f"Begin Location field found in PCI table: {begin_loc_pci_found}")
        print(f"End Location field found in PCI table: {end_loc_pci_found}")
        print("============================================")
        
    except Exception as e:
        import traceback
        print(f"ERROR: An exception occurred during script execution:\n{str(e)}")
        print(traceback.format_exc())
        
        # Try to save any incomplete but important data
        try:
            if 'aprx' in locals():
                aprx.save()
                print("Project saved despite error.")
        except:
            print("Could not save project after error.")

if __name__ == "__main__":
    find_midpoints_with_pci_matching()
