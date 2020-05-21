Models Available in AtModWeb
============================

.. _msis:

NRLMSISE00
++++++++++

This version of the venerable mass-spectrometer and incoherent scatter radar model
also incorporates mass density data derived from drag measurements and orbit determination.
It includes the same  database as the Jacchia family of models, and has been seen to outperform
both the older MSIS90 and the ubiquitous Jacchia-70. It's purpose is to specify the mass-density,
temperature and neutral species composition from the ground to the bottom of the exosphere
(around 1400km altitude). It provides number densities for the major neutral atmosphere constituents:
atomic and molecular nitrogen and oxygen, argon, helium and hydrogen. Additionally it includes a
species referred to as anomalous oxygen which includes O+ ion and hot atomic oxygen,
which was added to model these species' significant contributions to satellite drag at high latitude
and altitude, primarily during the summer months [picone]. The model inputs are the location, date,
and time of day, along with the 10.7 cm solar radio flux (F10.7) and the AP planetary activity index.

Variables Available for MSIS:
-----------------------------

* Temperature - the temperature of atmosphere in Kelvin
* mass - mass density of the atmosphere in g/cm^3
* HE - number density of helium in molecules/cm^3
* O - number density of atomic oxygen in molecules/cm^3
* N2 - number density of molecular nitrogen in molecules/cm^3
* O2 - number density of molecular oxygen in molecules/cm^3
* AR - number density of argon in molecules/cm^3
* H - number density of atomic hydrogen in molecules/cm^3
* N - number density of atomic nitrogen in molecules/cm^3
* AO - number density of 'Anomolous Oxygen' in molecules/cm^3
* T_exo - the temperature at the exobase (the highest altitude / top boundary of the model)

Technical Notes on Input Variables
----------------------------------

* UT, Local Time, and Longitude are used independently in the model and are not of equal importance for every situation. For the most physically realistic calculation these three variables should be consistent (SLT=SEC/3600+GLONG/15). The Equation of Time departures from the above formula for apparent local time can be included if available but are of minor importance.

* F107 and F107A values used to generate the model correspond to the 10.7 cm radio flux at the actual distance of the Earth from the Sun rather than the radio flux at 1 AU. 
The following site provides both classes of values: `NOAA NGDC/NCEI FTP <ftp://ftp.ngdc.noaa.gov/STP/SOLAR_DATA/SOLAR_RADIO/FLUX/>`_

References
----------

Picone, J. M., Hedin, A. E., Drob, D. P., and Aikin, A. C., NRLMSISE‐00 empirical model of the atmosphere: Statistical comparisons and scientific issues, J. Geophys. Res., 107( A12), 1468, `doi:10.1029/2002JA009430 <https://doi.org/10.1029/2002JA009430>>`_ , 2002


