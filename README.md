# AtModWeb
### _An web application for visually exploring (empirical) atmospheric models_
This is a project of the University of [Colorado Space Environment Data Analysis Group (SEDA)](http://www.ccar.int.colorado.edu/seda), a part of the Colorado Center for Astrodynamics Research (CCAR), and Aerospace Engineering Sciences (AES).

This tool was inspired by the similar IDL tool developed at National Center for Atmospheric Research's High Altitude Observatory (NCAR HAO) in 2003 as part of the Center for Integrated Space Weather Modeling (CISM) summer school.


### About 

AtModWeb is an easy to use and install Python/jQuery web application for plotting results from the Naval Research Laboratory Mass-Spec and Incoherent Scatter Radar Model of the neutral atmosphere ([NRLMSISE00](http://www.nrl.navy.mil/research/nrl-review/2003/atmospheric-science/picone/)). This model is maintained by NRL.

This tool currently allows users to plot variables such as the mass density, temperature and number densities of various major atmospheric chemical constituants (O, O2, N, Ar, N2, etc.). It allows uses to plot these against various position coordinates such as latitude, longitude and altitude, on pseudocolor (heatmap) plots, line graphs, or on top of various map projections. 

### Technical Details
The AtModWeb application is a complete application, from webserver to backend to frontend. After installation, simply running atmodweb.py will get you a webpage hosted from your machine. The webserver and backend use the [CherryPy](http://www.cherrypy.org/) python web framework, and the frontend (a single html and css file) is javascript/jQuery.

### Installation

On linux systems, (tested so far on Ubuntu 14.04, running the Anaconda python distribution), first ensure you have the following dependancies:
* Gfortran (`sudo apt-get install gfortran` on Ubuntu or use Anaconda) 
* [CherryPy](http://www.cherrypy.org/) (`pip install cherrypy` or `conda install cherrypy`)
* Numpy
* Matplotlib 
* Basemap (`conda install basemap` if using Anaconda, or `pip install basemap` to install from PyPI)
* [MsisPy](http://www.github.com/lkilcommons/msispy) - python wrapper for NRLMSISE00 Fortran code

Email me __liam.kilcommons at University of Colorado, Boulder (colorado.edu)__ for access to the model wrappers. Out of academic courtesy, they won't be released publicly until permission is given, though the wrappers themselves are GPLv3.

**Numpy, Matplotlib, and Gfortran dependancies can be satisfied by using the [Anaconda python distribution](http://continuum.io/downloads)**

Then:
```{sh}
git clone https://github.com/lkilcommons/atmodweb.git
cd atmodweb
python setup.py install 
```

Note that instead of `install` you can put `develop` if you will be altering the source code and don't want to reinstall after each change
This just symlinks the package to the source, which is handy.

### Running the Server
1. First, define an environment variable to tell CherryPy what your IP address is.
From a terminal (OSX or Linux):
`export CHERRYPY_IP=server.example.edu` 
Substitute server.example.edu with either your domain name or IP address, or just 'localhost' if you don't want your server 
accessible from the outside.
2. Start the server: `python atmodweb.py`
