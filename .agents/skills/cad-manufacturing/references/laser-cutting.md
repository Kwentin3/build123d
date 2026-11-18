# Laser-cut sheet output

Use the existing product exporter (mangal: `models/mangal/exports.py`) rather
than another CAD engine. DXF describes nominal 1:1 mm contours; the shop owns
kerf compensation. Verify closed contours, holes, duplicates, actual extents,
sheet thickness and BOM quantities using the existing ezdxf checks.

Material, stock tolerance, kerf and machine settings are independent inputs.
Do not convert CAD numerical tolerance into a shop tolerance. Fit requires a
representative coupon from the actual material/process and physical assembly.
Document missing production inputs and preserve NOT_CHECKED for untested fit,
hot behavior and stability. Existing clearance is a design parameter, not a
universal recommendation for every shop or material.
