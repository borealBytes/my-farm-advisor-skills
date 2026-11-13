# ISRIC SoilGrids standard soil-property legends (vendored)

Source: https://files.isric.org/soilgrids/former/2017-03-10/data/legends/
(accessed 2026-11-05). These are the official `soil.legends` palettes from
ISRIC/World Soil Information used to render SoilGrids property layers —
breakpoints set by quantiles on the global WoSIS profile compilation
(Hengl, GSIF/soil.legends documentation).

Columns: COLOR (decimal RGB)  NAME  DESCRIPTION  MINIMUM  MAXIMUM.
Units as published: ORCDRC = soil organic carbon g/kg; PHIHOX = pH x 10 in
water; BLDFINE = kg/m3; CECSOL = cmol/kg; SNDPPT/SLTPPT/CLYPPT = weight %;
RET10CM = water retention legend (absent in the 2017 dir; AWC — also a storage capacity — is mapped through the CECSOL ramp as documented proxy).

Do not restyle these ramps by hand — they are the domain-standard choropleth
scales; map SSURGO units onto them in the renderer instead.

2017-03-10 dir has no RET*.txt legend; the AWC->CECSOL mapping is the renderer's documented substitute.
