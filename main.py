import arcpy
import os
import math
import datetime

def find_midpoints_with_pci_matching():
    """
    1. Find midpoints of each line in WildomarPMPJordan feature layer
    2. Match these midpoints with records from PCI Differences table
    3. Create a points shapefile with the matched data and URLs for Mapillary and Google
    """
    try:
        print("Starting to access and match data...")
        
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
        
        # Try to find the StreetSec field or StreetID/SectionID fields
        street_sec_field = None
        street_id_field = None
        section_id_field = None
        
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
        
        # Determine field names in the PCI table
        print("\nLooking for key fields in the PCI Differences table...")
        pci_fields = arcpy.ListFields(pci_table)
        
        pci_street_id_field = None
        pci_section_id_field = None
        pci_diff_field = None
        
        for field in pci_fields:
            field_name = field.name
            
            if "STREET" in field_name.upper() and "ID" in field_name.upper():
                pci_street_id_field = field_name
                print(f"Found street ID field: {field_name}")
            if "SECTION" in field_name.upper() and "ID" in field_name.upper():
                pci_section_id_field = field_name
                print(f"Found section ID field: {field_name}")
            if "DIFF" in field_name.upper():
                pci_diff_field = field_name
                print(f"Found difference field: {field_name}")
        
        # Check if we have the necessary fields
        if not pci_street_id_field or not pci_section_id_field:
            print("ERROR: Could not find Street ID and Section ID fields in the PCI table.")
            return
        
        if not street_sec_field and (not street_id_field or not section_id_field):
            print("ERROR: Could not find StreetSec or Street ID/Section ID fields in the feature layer.")
            return
        
        # Create a dictionary to store PCI data for quicker lookups
        print("\nReading PCI Differences data...")
        pci_data = {}
        
        with arcpy.da.SearchCursor(pci_table, [pci_street_id_field, pci_section_id_field, pci_diff_field]) as cursor:
            for row in cursor:
                street_id = str(row[0]).strip()
                section_id = str(row[1]).strip()
                diff_value = row[2]
                
                # Create key in "Street_ID - Section_ID" format
                key = f"{street_id} - {section_id}"
                pci_data[key] = diff_value
        
        print(f"Loaded {len(pci_data)} records from PCI Differences table.")
        
        # Outputs in default GDB
        default_gdb = aprx.defaultGeodatabase
        print(f"\nCreating outputs in default geodatabase: {default_gdb}")
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = f"WildomarMidpoints_{timestamp}"
        midpoints_fc_name = f"{base_name}_Midpoints_Temp"
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
        shapefile_retrieve_fields = []
        
        # If we have a combined field, use it
        if street_sec_field:
            shapefile_retrieve_fields.append(street_sec_field)
        # Otherwise use separate fields
        else:
            shapefile_retrieve_fields.append(street_id_field)
            shapefile_retrieve_fields.append(section_id_field)
        
        # Now prepare to read the midpoints and join them with the original attributes
        midpoint_fields = ["SHAPE@"]
        results = []
        
        # Join fields from original data with midpoint geometries
        # First, create a dictionary of attributes from the original feature class
        attributes_dict = {}
        
        with arcpy.da.SearchCursor(wildomar_layer, shapefile_retrieve_fields) as cursor:
            for i, row in enumerate(cursor):
                # Determine the key based on available fields
                if street_sec_field:
                    street_sec_value = str(row[0]).strip()
                    key = street_sec_value
                    attributes_dict[i] = {
                        'street_id': street_sec_value,
                        'section_id': street_sec_value,
                        'combined_key': key
                    }
                else:
                    street_id_value = str(row[0]).strip()
                    section_id_value = str(row[1]).strip()
                    key = f"{street_id_value} - {section_id_value}"
                    attributes_dict[i] = {
                        'street_id': street_id_value,
                        'section_id': section_id_value,
                        'combined_key': key
                    }
        
        # Now read the midpoints and match them with attributes and PCI data
        print("\nMatching midpoints with attributes and PCI data...")
        match_count = 0
        no_match_count = 0
        
        with arcpy.da.SearchCursor(midpoints_fc_path, ["SHAPE@", "ORIG_FID"]) as cursor:
            for row in cursor:
                shape = row[0]  # SHAPE@
                orig_fid = row[1]  # ORIG_FID from feature to point operation
                
                # Get attributes from the dictionary using the ORIG_FID
                if orig_fid in attributes_dict:
                    attrs = attributes_dict[orig_fid]
                    street_id_value = attrs['street_id']
                    section_id_value = attrs['section_id']
                    key = attrs['combined_key']
                    
                    # Project the point to WGS84 for API URLs
                    pg = shape
                    proj = pg.projectAs(wgs84)
                    lon = proj.firstPoint.X
                    lat = proj.firstPoint.Y
                    
                    # Store original coordinates
                    original_x = shape.firstPoint.X
                    original_y = shape.firstPoint.Y
                    
                    # Check if this record matches a PCI record
                    if key in pci_data:
                        match_count += 1
                        diff_val = pci_data[key]
                        results.append({
                            'street_id': street_id_value,
                            'section_id': section_id_value,
                            'combined_key': key,
                            'diff_value': str(diff_val) if diff_val is not None else "",
                            'latitude': lat,
                            'longitude': lon,
                            'original_x': original_x,
                            'original_y': original_y,
                            'spatial_reference': layer_sr
                        })
                    else:
                        no_match_count += 1
                        # Include non-matches too if needed
                        results.append({
                            'street_id': street_id_value,
                            'section_id': section_id_value,
                            'combined_key': key,
                            'diff_value': "",  # No match in PCI data
                            'latitude': lat,
                            'longitude': lon,
                            'original_x': original_x,
                            'original_y': original_y,
                            'spatial_reference': layer_sr
                        })
        
        # Delete the temporary midpoints feature class
        arcpy.management.Delete(midpoints_fc_path)
        
        print(f"Found {match_count} matches with PCI data and {no_match_count} non-matches.")
        
        # Create final output table and feature classes
        table_name = base_name
        fc_name = f"{base_name}_Points"
        
        table_path = os.path.join(default_gdb, table_name)
        fc_path = os.path.join(default_gdb, fc_name)
        
        # 1. Create the table
        print(f"Creating table: {table_name}")
        arcpy.management.CreateTable(default_gdb, table_name)
        arcpy.management.AddField(table_path, "StreetID", "TEXT", field_length=50)
        arcpy.management.AddField(table_path, "SectionID", "TEXT", field_length=50)
        arcpy.management.AddField(table_path, "CombinedKey", "TEXT", field_length=100)
        arcpy.management.AddField(table_path, "DiffValue", "TEXT", field_length=50)
        arcpy.management.AddField(table_path, "Latitude", "DOUBLE")
        arcpy.management.AddField(table_path, "Longitude", "DOUBLE")
        arcpy.management.AddField(table_path, "MapillaryURL", "TEXT", field_length=255)
        arcpy.management.AddField(table_path, "GoogleURL", "TEXT", field_length=255)
        
        # Insert the data into the table
        print("Inserting data into the table...")
        with arcpy.da.InsertCursor(table_path, [
                "StreetID","SectionID","CombinedKey","DiffValue",
                "Latitude","Longitude","MapillaryURL","GoogleURL"
            ]) as ic:
            for r in results:
                lat = r['latitude']
                lon = r['longitude']
                # Generate API URLs for external services
                map_url = f"https://www.mapillary.com/app/user/view?lat={lat}&lng={lon}&z=18"
                g_url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}"
                ic.insertRow([
                    r['street_id'], r['section_id'], r['combined_key'],
                    r['diff_value'], lat, lon, map_url, g_url
                ])
        
        # Add the table to the map
        print("Adding the table to the map...")
        active_map.addDataFromPath(table_path)
        
        print(f"Successfully created table '{table_name}' with {len(results)} records.")
        
        # 2. Create points feature class - one set in original coordinate system and one in WGS84
        # First in the original spatial reference for use in ArcGIS
        original_fc_name = f"{base_name}_OrigPoints"
        original_fc_path = os.path.join(default_gdb, original_fc_name)
        
        print(f"\nCreating points feature class in original coordinate system: {original_fc_name}")
        arcpy.management.CreateFeatureclass(default_gdb, original_fc_name, "POINT", 
                                          spatial_reference=layer_sr)
        arcpy.management.AddField(original_fc_path, "StreetID", "TEXT", field_length=50)
        arcpy.management.AddField(original_fc_path, "SectionID", "TEXT", field_length=50)
        arcpy.management.AddField(original_fc_path, "CombinedKey", "TEXT", field_length=100)
        arcpy.management.AddField(original_fc_path, "DiffValue", "TEXT", field_length=50)
        arcpy.management.AddField(original_fc_path, "MapillaryURL", "TEXT", field_length=255)
        arcpy.management.AddField(original_fc_path, "GoogleURL", "TEXT", field_length=255)
        
        # Populate the original coordinate feature class
        print("Populating the original coordinate points feature class...")
        with arcpy.da.InsertCursor(original_fc_path, [
                "SHAPE@","StreetID","SectionID","CombinedKey",
                "DiffValue","MapillaryURL","GoogleURL"
            ]) as fic:
            for r in results:
                pt = arcpy.Point(r['original_x'], r['original_y'])
                pg = arcpy.PointGeometry(pt, r['spatial_reference'])
                lat = r['latitude']
                lon = r['longitude']
                map_url = f"https://www.mapillary.com/app/user/view?lat={lat}&lng={lon}&z=18"
                g_url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}"
                fic.insertRow([pg, r['street_id'], r['section_id'], r['combined_key'], 
                               r['diff_value'], map_url, g_url])
        
        # Now create the WGS84 version for external use
        print(f"\nCreating points feature class in WGS84: {fc_name}")
        arcpy.management.CreateFeatureclass(default_gdb, fc_name, "POINT", 
                                          spatial_reference=wgs84)
        arcpy.management.AddField(fc_path, "StreetID", "TEXT", field_length=50)
        arcpy.management.AddField(fc_path, "SectionID", "TEXT", field_length=50)
        arcpy.management.AddField(fc_path, "CombinedKey", "TEXT", field_length=100)
        arcpy.management.AddField(fc_path, "DiffValue", "TEXT", field_length=50)
        arcpy.management.AddField(fc_path, "MapillaryURL", "TEXT", field_length=255)
        arcpy.management.AddField(fc_path, "GoogleURL", "TEXT", field_length=255)
        
        # Populate the WGS84 feature class
        print("Populating the WGS84 points feature class...")
        with arcpy.da.InsertCursor(fc_path, [
                "SHAPE@","StreetID","SectionID","CombinedKey",
                "DiffValue","MapillaryURL","GoogleURL"
            ]) as fic:
            for r in results:
                pt = arcpy.Point(r['longitude'], r['latitude'])
                pg = arcpy.PointGeometry(pt, wgs84)
                map_url = f"https://www.mapillary.com/app/user/view?lat={r['latitude']}&lng={r['longitude']}&z=18"
                g_url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={r['latitude']},{r['longitude']}"
                fic.insertRow([pg, r['street_id'], r['section_id'], r['combined_key'], 
                               r['diff_value'], map_url, g_url])
        
        # Add the feature classes to the map
        print("Adding the feature classes to the map...")
        active_map.addDataFromPath(original_fc_path)
        active_map.addDataFromPath(fc_path)
        
        # Apply styling for better visibility of the points
        for lyr in active_map.listLayers():
            if lyr.isFeatureLayer and (original_fc_name in lyr.name or fc_name in lyr.name):
                symb = lyr.symbology
                if hasattr(symb, 'renderer'):
                    if hasattr(symb.renderer, 'symbol'):
                        symb.renderer.symbol.size = 8
                        symb.renderer.symbol.color = {'RGB': [255, 0, 0, 100]}
                        lyr.symbology = symb
        
        print(f"\nSuccessfully created feature classes with {len(results)} points.")
        print("Added to your active map.")
        
        # Save the project
        aprx.save()
        
        return {
            'table_path': table_path,
            'original_points_path': original_fc_path,
            'wgs84_points_path': fc_path
        }
    
    except Exception as e:
        print(f"ERROR: An error occurred: {str(e)}")
        import traceback
        print(traceback.format_exc())
        return None

if __name__ == "__main__":
    print("=== Finding Midpoints and Matching with PCI Data ===")
    out = find_midpoints_with_pci_matching()
    if out:
        print("\n=== COMPLETE ===")
        print(f"Table: {out['table_path']}")
        print(f"Original Points: {out['original_points_path']}")
        print(f"WGS84 Points: {out['wgs84_points_path']}")
    else:
        print("Failed to create outputs.")
