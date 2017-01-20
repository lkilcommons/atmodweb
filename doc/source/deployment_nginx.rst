AtModWeb Deployment behind Nginx Reverse Proxy
==============================================

This is a short tutorial on deploying atmodweb on a Ubuntu machine using Nginx reverse-proxy

We will assume that the server in question is running Ubuntu 14.04.

The IP for our server must be static and is xxx.xxx.xxx.xxx

First make sure the server is up to date, and install security software to prevent it being hacked, and install git so we can get the code, and gfortran so we can compile the model code.

.. code-block:: bash

	sudo apt-get update
	sudo apt-get upgrade
	sudo apt-get install fail2ban
	sudo apt-get install git
	sudo apt-get install gfortran
	
.. note:: If you get a strange error on starting atmodweb where python complains about not being able to find libSM.so.6, don't dispair. It is a `known anaconda issue` <https://github.com/ContinuumIO/anaconda-issues/issues/244>_ .The fix is to sudo apt-get install python-qt4.

The we make a non-root user so that we're not running AtModWeb as root (bad security practice).

.. code-block:: bash

	useradd atmodweb

.. code-block:: bash

	su atmodweb

Then we will set up the python distribution. We will be running AtModWeb from with the Ubuntu Python 2.7 system, within a virtual environment

.. code-block:: bash
	
	sudo apt-get install pip
	pip install virtualenv

Now we can set up the python virtualenv we will use to run AtModWeb

.. code-block:: bash
	
	cd ~
	virtualenv -p /usr/bin/python2.7 atmodweb --no-site-packages
	source atmodweb/bin/activate

Now we install the AtModWeb and the models it needs.

.. code-block:: bash

	cd ~
	git clone https://github.com/lkilcommons/atmodweb
	git clone https://github.com/lkilcommons/msispy
	
First we build the models' fortran code and then we can install the atmodexplorer and atmodweb:
	
.. note:: If you don't do these in order, they won't work, because msispy is a dependancy of atmodweb and isn't available thru pip

.. code-block:: bash

	cd ~/msis-project-name
	python setup.py install
	cd ~/atmodweb
	python setup.py install

Next we will install and configure NGINX

First install Nginx using the distribution package manager

.. code-block :: bash
	
	sudo apt-get install nginx

By default (on Ubuntu) nginx will put its config files in /etc/nginx/conf.d

Now we configure the reverse-proxy to redirect incoming HTTP traffic to the atmodweb installation
(this is based on `CherryPy Documentation <http://docs.cherrypy.org/en/latest/deploy.html#id4>`_)

Here is a starting point for the Nginx configuration
.. code-block :: nginx

	upstream atmodwebs {
	   server 127.0.0.1:8080;
	}

	gzip_http_version 1.0;
	gzip_proxied      any;
	gzip_min_length   500;
	gzip_disable      "MSIE [1-6]\.";
	gzip_types        text/plain text/xml text/css
	                  text/javascript
	                  application/javascript;

	server {
	   listen 80;
	   server_name  www.example.com;

	   access_log  /atmodweb/logs/www.example.com.log combined;
	   error_log  /atmodweb/logs/www.example.com.log;

	   location ^~ /www/  {
	      root /atmodweb/www/;
	   }

	   location / {
	      proxy_pass         http://atmodwebs;
	      proxy_redirect     off;
	      proxy_set_header   Host $host;
	      proxy_set_header   X-Real-IP $remote_addr;
	      proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
	      proxy_set_header   X-Forwarded-Host $server_name;
	   }
	}

.. code-block :: nginx

	worker_processes 1;

	events {

	    worker_connections 1024;

	}

	http {

	    sendfile on;

	    gzip              on;
	    gzip_http_version 1.0;
	    gzip_proxied      any;
	    gzip_min_length   500;
	    gzip_disable      "MSIE [1-6]\.";
	    gzip_types        text/plain text/xml text/css
	                      text/comma-separated-values
	                      text/javascript
	                      application/x-javascript
	                      application/atom+xml;

	    # Configuration containing list of application servers
	    upstream app_servers {

	        server 127.0.0.1:8080;
	        # server 127.0.0.1:8081;
	        # ..
	        # .

	    }

	    # Configuration for Nginx
	    server {

	        # Running port
	        listen 80;

	        # Settings to serve static files 
	        #location ^~ /www/  {
	        #
	            # Example:
	            # root /full/path/to/application/static/file/dir;
	        #    root /home/atmodweb/atmodweb/www;
	        #
	        #}

	        # Serve a static file (ex. favico)
	        # outside /static directory
	        #location = /favico.ico  {
	        #
	        #    root /home/atmodweb/atmodweb/favico.ico;
	        #
	        #}

	        # Proxy connections to the application servers
	        # app_servers
	        location /atmodweb {

	            proxy_pass         http://app_servers;
	            proxy_redirect     off;
	            proxy_set_header   Host $host;
	            proxy_set_header   X-Real-IP $remote_addr;
	            proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
	            proxy_set_header   X-Forwarded-Host $server_name;

	        }
	    }
	}


.. warning:: This config allows the possibility of multiple instances of the application running (just add another 'server' to the 'upstream'). However doing this for AtModWeb is not a good idea, since the application doesn't have a shared database (currently), and so there is no way for the second instance of the application to know about the first's users and visa-versa, so a user would consantly have to relogin as her requests are load-balanced between the different AtModWeb instances. 

Finally we will configure the installation of atmodweb by setting a few environment variables in our .bashrc.
Replace the values here with something appropriate for your server (i.e. xxx.xxx.xxx.xxx with your IP or hostname),
and if you want to password protect your server, an approriately strong password and username. This uses CherryPy's digest authentication.
If either environment variable (CHERRYPY_USER or CHERRYPY_PWD) doesn't exist, the server will not be password protected.

.. code-block:: bash

	#in .bashrc, add this line
	export ATMODWEB_ROOT_DIR='/var/www/atmodweb'
	#if you want to password protect your site, add these too
	export CHERRYPY_USER='my_user'
	export CHERRYPY_PWD='my_password'


