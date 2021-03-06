AtModWeb Deployment on Digital Ocean
====================================

This is a short tutorial on deploying atmodweb on the Digital Ocean virtual private server service.

We will use a $20/mo droplet which is allocated 2 GB of RAM and 2 processors.

We will install Ubuntu 14.04, and log in using an SSH key. Please see the Digital Ocean documentation
for more information on how to do this.

The IP for our droplet is xxx.xxx.xxx.xxx

We'll use terminal and SSH to get into the droplet. Since we've enabled SSH key login, we won't need to
enter a password.

.. code-block:: bash

	ssh root@xxx.xxx.xxx.xxx

First make sure the droplet is up to date, and install security software to prevent it being hacked, and install git so we can get the code, and gfortran so we can compile the model code.

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

Then we will download the anaconda python distribution. The easy way to do this is to navigate to the 
Anaconda site, right click the link to the installation script and copy the link location. Then you
can paste it into the terminal that is SSH'ed into the droplet

.. code-block:: bash

	cd ~ 
	wget <paste-long-numerical-url-to-Anaconda-*.sh-here>
	bash Anaconda<tab>

Hitting tab when typing (at <tab>) will autocomplete the Anaconda shell command. We'll just install Anaconda to /home/atmodweb/anaconda (the default)

Anaconda will do it's thing and then ask 'Do you wish the installer to prepend the Anaconda install location
to PATH in your /home/liamk/.bashrc?', which we will answer with 'yes'. This will make anaconda the default python (i.e. if you type python you get the anaconda python and not the one in /usr/bin/python )

Now we make sure anaconda is up to date:

.. code-block:: bash

	source ~/.bashrc
	conda update conda

And install the requirements of AtModWeb (BaseMap may take awhile, it often needs the newest numpy and matplotlib as well)

.. code-block:: bash

	conda install basemap
	pip install cherrypy

.. warning:: Do not try to install atmodweb and atmodexplorer without first installing the dependancies. There is still work to be done it make the setup.py dependancies totally inclusive so that everything can be 'python setup.py install'ed

Now we install the AtModWeb and the models it needs. Contact the maintainer of this repo to learn what the urls are for the private model repos and to get your github account approved to be able to download them. This is a matter of academic curtosy to the maintainers of the models, who have not yet cleared us to release them publicly.

.. code-block:: bash

	cd ~
	git clone https://github.com/lkilcommons/atmodexplorer
	git clone https://github.com/lkilcommons/atmodweb
	git clone https://github.com/lkilcommons/<MSIS-project-name> 
	git clone https://github.com/lkilcommons/<HWM-project-name> 

First we build the models' fortran code and then we can install the atmodexplorer and atmodweb:
	
.. note:: If you don't do these in order, they won't work, because msispy and hwmpy are dependancies of atmodexplorer, and atmodexplorer is a dependancy of atmodweb

.. code-block:: bash

	cd ~/msis-project-name
	python setup.py develop
	cd ~/hwm-project-name
	python setup.py develop
	cd ~/atmodexplorer
	python setup.py develop
	cd ~/atmodweb
	python setup.py develop
	
Finally we will configure the installation of atmodweb by setting a few environment variables in our .bashrc.
Replace the values here with something appropriate for your server (i.e. xxx.xxx.xxx.xxx with your IP or hostname),
and if you want to password protect your server, an approriately strong password and username. This uses CherryPy's digest authentication.

.. code-block:: bash

	#in .bashrc, add this line
	export CHERRYPY_IP='xxx.xxx.xxx.xxx'
	#if you want to password protect your site, add these too
	export CHERRYPY_USER='my_user'
	export CHERRYPY_PWD='my_password'

.. note:: If you want to run your instance using the normal web port (80), you will need to issue the following firewall rule. You cannot bind the cherrypy server directly to 80 (unless you are running as root, which is BAD SECURITY), so you will need to redirect. 

How to run on port 80:

.. code-block:: bash
iptables -t nat -A PREROUTING -p tcp --dport 80 -j REDIRECT --to-port 8080

