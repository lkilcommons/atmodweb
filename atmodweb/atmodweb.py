import cherrypy #Python web server
import mpld3 #Render a matplotlib figure as a javascript d3 object
#Main imports
import numpy as np
import sys, pdb, textwrap, datetime,os,time
import socket #to figure out our hostname
import matplotlib as mpl
import matplotlib.pyplot as pp

from mpl_toolkits.basemap import Basemap
from matplotlib import ticker
from matplotlib.colors import LogNorm, Normalize
from collections import OrderedDict
import logging
logging.basicConfig(level=logging.INFO)

from cherrypy.lib import auth_digest


#Import the model running code
from atmodexplorer.atmodbackend import ModelRunner, MsisRun, ModelRun, PlotDataHandler

class ansicolors:
	HEADER = '\033[95m'
	OKBLUE = '\033[94m'
	OKGREEN = '\033[92m'
	WARNING = '\033[93m'
	FAIL = '\033[91m'
	ENDC = '\033[0m'
	BOLD = '\033[1m'
	UNDERLINE = '\033[4m'

class ControlState(dict):
	"""
	Subclass dict to make a dictionary that handles synchronizing with the cherrypy session before getting and after setting

	TODO Document Controlstate
	"""
	def __init__(self, *args):
		self._sync = False #Add a flag to determine whether or not we sync with the session on set/get
		self._bound_meth = dict()
		self.last = dict() 
		dict.__init__(self, args)
		
	@property
	def sync(self):
		return self._sync
	
	@sync.setter
	def sync(self, value):
		oldval = self._sync
		self._sync = value
		if value and not oldval: #If we've switched to syncing
			self.push() #Force an update of the session
	

	def __setitem__(self, key, value):

		dict.__setitem__(self, key, value)
		if self.sync:
			cherrypy.session[key]=value
		if key in self._bound_meth:
			for meth in self._bound_meth[key]:
				print "~~~~Controlstate TRIGGERING BOUND METHOD %s of key %s new value %s ~~~~" % (meth.__name__,str(key),str(self[key]))
				meth()
		
		
	def __getitem__(self, key):
		if self.sync:
			value = cherrypy.session.get(key)
			if value is not None:
				dict.__setitem__(self,key,value) #Make sure local copy is up to date
			else:
				return dict.__getitem__(self,key)
		else:
			value = dict.__getitem__(self, key)
		return value

	def push(self):
		"""
		Update the session with the dictionary contents
		"""
		for key in self:
			if cherrypy.session.has_key(key):
				logging.warn('Overwriting already-existing key %s in session.\n' % (key))
			cherrypy.session[key] = dict.__getitem__(self,key)
	
	def bind_changed(self,key,meth):
		"""
		Binds a method with no inputs to call when the controlstate item corresponding to key is called
		"""
		if key in self._bound_meth:
			self._bound_meth[key].append(meth)
		else:
			self._bound_meth[key] = [meth]

	def trigger_changed(self,key,**kwargs):
		"""
		Triggers a bound on changed method corresponding to key
		Allows specification of keyword arguments (as oppssed to setting the value, which doens't)
		Specifically this gets used when setting subelements of dictionarys in this dictionary
		because that doesn't trigger a '__set__'
		"""
		for meth in self._bound_meth[key]:
			meth(**kwargs)


	def ashtml(self,key):
		"""
		Returns value at key as html to the best of it's ability
		"""
		htmllines = []
		typestr = lambda x: str(type(x)).replace('<','(').replace('>',')')
		if key in self:
			item = self[key]
			if isinstance(item,dict):
				#It's a dictionary, render it as a ul
				htmllines.append('<ul ID="controlstate_%s">' % (key))
				for ikey in item:
					htmllines.append('<li ID="controlstate_%s_%s"> %s (%s) </li>' % (str(key),str(ikey),str(item[ikey]),typestr(item[ikey])))
				htmllines.append('</ul>')
			elif isinstance(item,list):
				#Array or similar, render as ol
				htmllines.append('<ol ID="controlstate_%s">' % (key))
				for iind in range(len(item)):
					htmllines.append('<li ID="controlstate_%s_%s"> %s (%s) </li>' % (str(key),str(iind),str(item[iind]),typestr(item[iind])))
				htmllines.append('</ol>')
			else:
				#Render as a p
				htmllines.append('<p ID="controlstate_%s">%s %s </p>' % (str(key),str(item),typestr(item)))
		else:
			raise ValueError('No such key in controlstate %s' % (key))
		return "".join(htmllines)

	def copyasdict(self):
		"""
		Returns a copy ControlState as a normal dictionary
		"""
		newdict = dict()
		for key in self:
			newdict[key] = dict.__getitem__(self,key)
		return newdict

	def updatelast(self):
		"""
		Update the "historical" copy of itself
		"""
		mycopy = self.copyasdict()
		for key in mycopy:
			self.last[key] = mycopy[key]

	def changed(self,key):
		"""
		Is the current value assigned to key changed since last updatelast call?
		"""
		if key in self.last:
			return self.last[key] != self[key]
		else:
			logging.warn(ansicolors.WARNING+"Key %s not in controlstate memory\n" % (key)+ansicolors.ENDC)
			return True

class UiHandler(object):
	"""
	A class to hold the state of the UI controls and settings.
	The UiHandler processes requests from the browser (i.e. GET, SET, POST)
	
	"""
	exposed = True
	def __init__(self,amwo):
		self.amwo = amwo #Parent atmodweb object
		self.default_controlstate = {'model_index':-1,'datetime':{'year':2000,'month':6,'day':21,'hour':12,'minute':0,'second':0},\
			'lat':40.0274,'lon':105.2519,'alt':110.,\
			'plottype':'pcolor',\
			'xvar':'Longitude','xbounds':[-180.,180.],'xnpts':50.,'xlog':False,'xmulti':False,\
			'yvar':'Latitude','ybounds':[-90.,90.],'ynpts':50.,'ylog':False,'ymulti':False,\
			'zvar':'Temperature','zbounds':[0.,1000.],'zlog':False,'zmulti':False,\
			'modelname':'msis','differencemode':False,'run_model_on_refresh':True,
			'lastplot':None,'recentplots':[],'lastcaption':None,'recentcaptions':[],
			'drivers':{'dt':datetime.datetime(2000,6,21,12,0,0)}}

		self.controlstate = ControlState()
		self.initcontrolstate()


	def initcontrolstate(self):
		#Fill up the controlstate instance
		for key in self.default_controlstate:
			self.controlstate[key]=self.default_controlstate[key]
		self.controlstate.updatelast() #Make sure we start life with a history

	def output_sanitize(self,indata):
		"""
		Turns output into something serializable
		Cherrypy is pretty good about doing this itself. Basically all I handle right now is datetime
		"""

		if isinstance(indata,dict):
			outdata = indata.copy()
			for k in outdata:
				outdata[k] = self.output_sanitize(outdata[k])
		elif isinstance(indata,datetime.datetime):
			outdata = indata.strftime('%Y-%m-%d %H:%M:%S')
		else:
			outdata = indata
		return outdata

	@cherrypy.tools.accept(media='text/plain')
	@cherrypy.tools.json_out()
	def GET(self, statevar, subfield=None):
		"""
		ReST GET request handler (i.e. browser tells backend information and backend stores that information) 
		Returns JSONified dictionary. 
		The RESTful API here is all based on setting and getting values from the ControlState dictionary subclass.

		INPUTS
		------
			statevar - string
				Which key of self.controlstate will be retrieved with this request 
			subfield - string,optional
				If self.controlstate[statevar] is a dictionary, then the value at self.controlstate[statevar][subfield] will
				be retrieved if subfield is not None

		RETURNS
		-------
			retjson - dict
				A dictionary response to the request. Has a key of the input statevar, the value of which is the desired data.
				Does NOT ever have a key of subfield.
		"""
		retjson = dict()
		if statevar in self.controlstate and subfield is None:
			retval = self.controlstate[statevar]
			logging.info(ansicolors.OKGREEN+'GET for statevar:%s returning %s\n' % (statevar,str(retval))+ansicolors.ENDC)
		elif statevar in self.controlstate and subfield is not None:
			if hasattr(self.controlstate[statevar],'__getitem__'): #Must be some kind of dict like thing
				retval = self.controlstate[statevar][subfield]
				logging.info(ansicolors.OKGREEN+'GET for statevar:%s, key:%s returning %s\n' % (statevar,subfield,str(retval))+ansicolors.ENDC)
			else: #Just try to do the thing UNSAFE
				if hasattr(self.controlstate[statevar],subfield):
					mymeth = getattr(self.controlstate[statevar],subfield)
					retval = mymeth
					logging.warn(ansicolors.WARNING+"UNSAFE GET Eval %s = self.controlstate[%s].%s()" % (str(retval),statevar,str(subfield))+ansicolors.ENDC)
		elif statevar == 'controlstate':
			retval=dict()
			for key in self.controlstate:
				if self.controlstate.changed(key):
					retval[key]=self.controlstate.ashtml(key)	
		retjson[statevar]=self.output_sanitize(retval)
		return retjson

	@cherrypy.tools.accept(media='text/plain')
	@cherrypy.tools.json_out()
	def POST(self, posttype=None):
		"""
		ReST POST request handler (i.e. browser tells backend information and backend does something based on that information) 
		Returns JSONified dictionary. 

		INPUTS
		------
			posttype - string
				Which POST request to evaluate

			
		RETURNS
		-------
			retjson - dict
				A dictionary response to the request. Gets converted to json by cherrypy. For POST requests this
				is kind of a dummy response, because jQuery assumes that a PUT that doesn't respond has failed.
				All it is is a dictionary with one field, keyed to the input statevar, and valued to True
		
		'uiready' - Starts controlstate syncing with CherryPy session
		'refreshnow' - Calls the FakeCanvas method 'refresh' to process any enqued changes to the plot
		'replotnow' - Calls the AtModWebObj method 'replot' to write the FakeCanvas matplotlib figure to a file 
						and update the 'lastplot' key in controlstate
		'refreshselect' - Calls the FakeCanvas method refreshSelectOptions, which checks the controlstate x, y and z vars, and the plottype and sets 
							the appropriate possible choices of variables to plot for x, y and z
		'refreshmodeloptions' - Updates the controlstate 'drivers' key from the last model run (ModelRun instance)
		'debugreinit' - A 'panic'. Reinits the controlstate to its default values, and does all of the above as well. 

		"""
		if posttype in self.controlstate:
			retval = self.controlstate[posttype]
			logging.info(ansicolors.HEADER+'POST for posttype:%s returning %s\n' % (posttype,str(retval))+ansicolors.ENDC)
			return {posttype:retval}
		elif posttype == 'uiready':
			#Begin syncing the local controlstate with the session
			logging.info(ansicolors.HEADER+'POST for posttype:%s beginning controlstate sync\n' % (posttype)+ansicolors.ENDC)
			self.controlstate.sync = True
			return {"uiready":True}
		elif posttype == 'refreshnow':
			self.amwo.canvas.refresh()
			logging.info(ansicolors.HEADER+'POST for posttype:%s successful refresh\n' % (posttype)+ansicolors.ENDC)
			return {"refresh":True}
		elif posttype == 'replotnow':
			newfn,newcap = self.amwo.replot()
			logging.info(ansicolors.HEADER+'POST for posttype:%s successful replot: new file=%s \n' % (posttype,newfn)+ansicolors.ENDC)
			return {"src":newfn,"cap":newcap}
		elif posttype == 'refreshselect':
			self.amwo.canvas.refreshSelectOptions()
			logging.info(ansicolors.HEADER+'POST for posttype:%s successful refresh select options\n' % (posttype)+ansicolors.ENDC)
			return {"refreshselect":True}
		elif posttype == 'autoscale':
			self.amwo.canvas.autoscale()
			logging.info(ansicolors.HEADER+'POST for posttype:%s successful refresh variable limits\n' % (posttype)+ansicolors.ENDC)
			return {"autoscale":True}
		elif posttype == 'refreshmodeloptions':
			newfn = self.amwo.canvas.refreshModelRunOptions()
			logging.info(ansicolors.HEADER+'POST for posttype:%s successful refresh model run options\n' % (posttype)+ansicolors.ENDC)
			return {"refreshmodeloptions":True}
		elif posttype == 'debugreinit':
			cherrypy.lib.sessions.expire()
			self.initcontrolstate()
			self.controlstate.push()
			self.amwo.canvas.refreshSelectOptions()
			self.amwo.canvas.autoscale()
			self.amwo.canvas.refreshModelRunOptions()
			logging.info(ansicolors.HEADER+'POST for posttype:%s successfully reintialized local controlstate\n' % (posttype)+ansicolors.ENDC)
			return {"debugreinit":True}

	def input_sanitize(self,inval):
		"""
		Sanitize data that came from a browser PUT request. This method handles inputs that are lists (i.e passed as JS arrays),
		and inpus that are dicts (i.e. passed as JS objects)
		It calls input_sanitize_single to process individual values.
		"""
		#Sanitize input
		if isinstance(inval,list):
			outval = []
			for v in inval:
				#Recursion FTW
				outval.append(self.input_sanitize(v))
		elif isinstance(inval,dict):
			outval = dict()
			for key in inval:
				#More recursion
				outval[key] = self.input_sanitize(inval[key])
		elif ',' in inval: #Maybe its a string trying to represent a list
			inval = inval.split(',')
			#Now recurse with list of strings and no commas
			self.input_sanitize(inval)
		else:
			outval = self.input_sanitize_single(inval)
		return outval

	def input_sanitize_single(self,val):
		"""
		Turns request data from PUT requests into something python knows what to do with. First it converts the strings from unicode
		to ASCII, and then trys to guess what the string is intended to be by trying to turn into an int, float, bool, or datetime.datetime
		using the format: Y-m-d H:M:S. If it fails all these, it just returns the string.
		"""

		#Convert a unicode string returned with a put into a python
		#datatype in a sensible way
		#Check if it's a bool
		#First try to turn the unicode into a normal string
		try:
			val = val.encode('ascii','ignore')
		except:
			pass
		val = val.strip() #Remove any leading or trailing whitespace

		#Make sure there's no spaces, parens, brackets or other nonsense
		nonsense = ['(',')','[',']','{','}',';','/']
		if any([ns in val for ns in nonsense]):
			for char in nonsense:
				val = val.replace(char,'') 
		

		#Check if it's just an integer
		if val.isdigit(): #isdigit returns false if theres a .
			val = int(val)
		#Check if it's able to be turned into a float
		elif '.' in val: 
			floatable=True
			try:
				val = float(val)
			except ValueError:
				floatable=False

		#Check for bool
		if val in ['true','True','on']:
			val=True
		elif val in ['false','False','off']:
			val=False

		#Try to convert it to a datetime
		try:
			val = datetime.datetime.strptime(val,'%Y-%m-%d %H:%M:%S')
		except:
			print "failed to convert %s to datetime\n" % (val)
			pass

		return val

	@cherrypy.tools.json_out()
	@cherrypy.tools.accept(media='text/plain')
	def PUT(self,statevar=None,newval=None,subfield=None):
		"""
		ReST PUT request handler. Returns JSONified dictionary. 
		The RESTful API here is all based on setting and getting values from the ControlState dictionary subclass.
		
		INPUTS
		------
			statevar - string
				Which key of self.controlstate will be set with this request 
			newval - anything
				What will be stored at self.controlstate[statevar]
			subfield - string,optional
				If self.controlstate[statevar] is a dictionary, then newval will be stored at self.controlstate[statevar][subfield] if 
				subfield is not None

		RETURNS
		-------
			retjson - dict
				A dictionary response to the request. Gets converted to json by cherrypy. For PUT requests this
				is kind of a dummy response, because jQuery assumes that a PUT that doesn't respond has failed.
				All it is is a dictionary with one field, keyed to the input statevar, and valued to "True"
		"""
		if newval is not None:
			newval = self.input_sanitize(newval)

		if subfield is None: #Top level put
			logging.info(ansicolors.OKBLUE+'PUT request for statevar:%s new value %s, type: %s \n' % (str(statevar),str(newval),str(type(newval)))+ansicolors.ENDC)
			if statevar in self.controlstate:
				self.controlstate[statevar] = newval
			else:
				raise RuntimeError('PUT request with invalid controlstate addressee %s, data: %s' % (str(statevar),str(newval)))
		else: 
			logging.info(ansicolors.OKBLUE+'PUT request for statevar:%s, subfield:%s, new value %s, type: %s \n' % (str(statevar),str(subfield),str(newval),str(type(newval)))+ansicolors.ENDC)
			if hasattr(self.controlstate[statevar],'__setitem__'): #Must be some kind of dict like thing
				self.controlstate[statevar][subfield] = newval
				#Have to explicitly trigger changed since we aren't explicitly 
				#setting controlstate['drivers'] TODO find a better way
				self.controlstate.trigger_changed(statevar,subfield=subfield)
			elif hasattr(self.controlstate[statevar],subfield):
				myattr = getattr(self.controlstate[statevar],subfield)
				myattr = newval
				logging.warn("UNSAFE PUT Eval setattr(self.controlstate[%s],%s,%s)" % (statevar,str(subfield),str(newval)))				
			else:
				raise RuntimeError('PUT request with invalid controlstate addressee %s.%s, data: %s' % (str(statevar),str(subfield),str(newval)))
		#self.amwo.canvas.refresh()
		#Return something to make jquery happy (a request that returns nothing has state "rejected")
		return {statevar:"True"}

	#def DELETE(self):
	#	cherrypy.session.pop('mystring', None)

class FakeCanvas(object):
	"""
	The FakeCanvas is the workhorse of the backend of AtModWeb. It's called a FakeCanvas because of the project this 
	was based off of, the AtModExplorer. This takes the place of the matplotlib canvas subclass, that 
	preformed a similar function in atmodexplorer.
	It is a matplotlib canvas is the sense that it has one matplotlib figure at self.fig, and an axes at self.ax. But
	otherwise it's just a convenient way of organizing the code and has nothing to do with Matplotlib.
	It's important parameters are the PlotDataHandler instance as self.pdh, and the ControlState instance at self.controlstate
	It's parent, the AtModWebObj that ties the application together is at self.atmo. It shares it's controlstate with the UiHandler,
	which handles requests.

	"""
	def __init__(self,atmo,controlstate):		
		self.atmo = atmo #"parent" atmodwebobject
		self.fig = pp.figure()
		self.caption = 'caption' # Caption for the figure, created by make_caption 
		self.ax = self.fig.add_subplot(111)
		self.controlstate = controlstate
		self.pdh = PlotDataHandler(self)
		#Do a first run of the model
		self.initModelRunner()
		#Bind on changed methods
		self.controlstate.bind_changed('plottype',self.refreshSelectOptions)
		self.controlstate.bind_changed('xbounds',self.xbounds_changed)
		self.controlstate.bind_changed('ybounds',self.ybounds_changed)
		self.controlstate.bind_changed('xvar',self.xvar_changed)
		self.controlstate.bind_changed('yvar',self.yvar_changed)
		self.controlstate.bind_changed('zvar',self.zvar_changed)
		self.controlstate.bind_changed('datetime',self.datetime_changed)
		self.controlstate.bind_changed('drivers',self.drivers_changed)
		


	def initModelRunner(self):
		"""Does a first run of the model specified in the controlstate to make sure that there's a reference run. 
		A lot of code looks to the previously run model (i.e. to populate the selects for x, y and z)"""

		self.mr = ModelRunner(model=self.controlstate['modelname'])
		
		#Make sure the default selection is sane and set the appropriate things in the next model run instance
		self.prepare_model_run()

		#Now run the model
		self.mr.nextrun.populate()
		#Append the model run to the runs database
		self.mr()
		

	def refreshModelRunOptions(self):
		"""To be called whenever a new model run is instantiated. Updates all controlstate options which change with model run"""
		#Update the drivers dictionary in
		self.pdh.clear_data()
		self.controlstate['drivers']=self.mr.runs[-1].drivers.copy()

	def autoscale(self):
		"""Updates the xbounds,ybounds and zbounds in the controlstate from the lims dictionary in last model run"""
		xdata,xlims = self.mr[self.controlstate['xvar']] #returns data,lims
		ydata,ylims = self.mr[self.controlstate['yvar']] #returns data,lims
		zdata,zlims = self.mr[self.controlstate['zvar']] #returns data,lims

		self.controlstate['xbounds']=xlims
		self.controlstate['ybounds']=ylims
		self.controlstate['zbounds']=zlims

	def drivers_changed(self,subfield=None):
		"""On changed to controlstate['drivers'], update the next model run drivers"""
		#Currently done in referesh?
		if subfield is None:
			#Update anything that is currently defined in the ModelRun subclass' __init__ under drivers
			#for key in self.mr.nextrun.drivers:
			#	if key in self.controlstate['drivers']:
			#		self.mr.nextrun.drivers[key] = self.controlstate['drivers'][key]
			#Do Nothing
			pass
		else:
			self.mr.nextrun.drivers[subfield] = self.controlstate['drivers'][subfield]
		

	def datetime_changed(self,subfield=None):
		"""Process a change in controlstate['datetime'] dict by setting controlstate['drivers']['dt']"""
		#Needs subfield kwarg
		#Convert the dict to an actual datetime
		dt = datetime.datetime(**self.controlstate['datetime'])
		self.controlstate['drivers']['dt'] = dt
		#Have to explicitly trigger changed since we aren't explicitly 
		#setting controlstate['drivers'] TODO find a better way
		self.controlstate.trigger_changed('drivers',subfield='dt')
	
	def xvar_changed(self):
		"""Updates the xbounds in the controlstate when a new xvar is selected"""
		xdata,xlims = self.mr[self.controlstate['xvar']] #returns data,lims, works for multi
		self.controlstate['xbounds']=xlims

	def yvar_changed(self):
		"""Updates the ybounds in the controlstate when a new yvar is selected"""
		ydata,ylims = self.mr[self.controlstate['yvar']] #returns data,lims, works for multi
		self.controlstate['ybounds']=ylims

	def zvar_changed(self):
		"""Updates the zbounds in the controlstate when a new zvar is selected"""
		zdata,zlims = self.mr[self.controlstate['zvar']] #returns data,lims, works for multi
		self.controlstate['zbounds']=zlims

	def xbounds_changed(self):
		"""Function which is called whenever the xbounds are changed in the controlstate. Changes limits for next model run"""
		if not self.is_multi('x') and self.is_position('x'): 
			self.mr.nextrun.lims[self.controlstate['xvar']] = self.controlstate['xbounds']
	
	def ybounds_changed(self):
		"""Function which is called whenever the ybounds are changed in the controlstate. Changes limits for next model run"""
		if not self.is_multi('y') and self.is_position('y'): 
			self.mr.nextrun.lims[self.controlstate['yvar']] = self.controlstate['ybounds']
	
	#Set what we are allowed to plot
	def refreshSelectOptions(self):
		"""
		Creates the (x,y,z)var_options JSON-style dictionaries used to populate the variable select elements. 
		Relies on the PlotDataHandler plot properies settings to figure out what are allowed variables
		for x, y and z axes for a particular type of plot (i.e. a 'map' type plot can only have 'Longitude' as 'xvar'
		'Latitude' as 'yvar' and anything as 'zvar').
		Get the current plottype from the controlstate, instead of using the PlotDataHandler setting, because
		the plotDataHandler setting is only updated when the 'refresh' method is called, and front end needs to know
		what the available variables are to populate the HTML select element for picking variables.
		"""

		allowed = dict()
		allowed['x'] = self.plotProperty('x_allowed')
		allowed['y'] = self.plotProperty('y_allowed')
		allowed['z'] = self.plotProperty('z_allowed')

		all_options_dict = dict()
		for k in self.mr.runs[-1].vars.keys():
			all_options_dict[k]=k


		for var in ['x','y','z']:
			options_dict = dict()
			#Short circuting options
			if 'all' in allowed[var]:
				options_dict=all_options_dict.copy()	
			elif 'none' in allowed[var]:
				pass #Return an empty
			#Iterate through list of allowed values
			else:
				for value in allowed[var]:
					if value == 'position':
						for k in all_options_dict:
							if all_options_dict[k] in self.mr.nextrun.vars: #Only position (input) variables are in a run before execution 
								options_dict[k] = all_options_dict[k]
					elif value == 'notposition':
						for k in all_options_dict:
							if all_options_dict[k] not in self.mr.nextrun.vars: #Only position (input) variables are in a run before execution 
								options_dict[k] = all_options_dict[k]
					elif value in all_options_dict:
						options_dict[value]=value
			self.controlstate[var+'var_options']=options_dict

		
	def plotProperty(self,prop):
		"""Simple convenience function to retrieve a property of the current type of plot"""
		#Current plottype
		cpt = self.controlstate['plottype']
		return self.pdh.plottypes[cpt][prop]


	def is_multi(self,coord):
		"""
		Convenience function for testing whether the currently selected x or y variables (controlstate['xvar'],etc) are multiple vars
		i.e. stored as lists internally.
		"""
		return hasattr(self.controlstate[coord+'var'],'__iter__') #just tests if the controlstate is a list/tuple
			
	def is_position(self,coord):
		"""
		Convenience function for testing whether the currently selected x or y variables are positions. 
		i.e do they have names 'Latitude','Longitude' or 'Altitude'. 
		Handles the possibility of the variables being multiple variables on the same axes, so this is
		preferred way of checking instead of 
		
		.. code-block :: <python>
			self.controlstate['xvar'] in ['Latitude','Longitude','Altitude'] 
		"""
		if not self.is_multi(coord):
			return self.controlstate[coord+'var'] in self.mr.nextrun.vars
		else:
			return any(v in self.mr.nextrun.vars for v in self.controlstate[coord+'var'])  

	def prepare_model_run(self):
		"""
		Determines which position variables (lat,lon, or alt) are constant,
		given the current settings of the xvar, yvar and zvar.
		
		Tells the ModelRun instance that is about to be populated with data,
		i.e. the model is going to run, what shape that data will be. 

		If it's a line we are plotting we only need 1-d data in the model and can save some time, 
		but if we will be plotting a pcolor or map, we'll need 2-d data. 
		
		Also tells that ModelRun which position variables will constant,
		and which independant: i.e. if we are plotting a 'Temperature'
		vs. 'Altitude' plot, then we want to determine which latitude
		and longitude values the user wants the model to calculate the altitude profile
		for from the controlstate (and lat and lon will be constant for the model run).

		"""
	
		#Begin by assigning all of the position variables their approprate output
		#from the controls structure. These are all single (scalar) values set by
		#the QLineEdit widgets for Lat, Lon and Alt.
		#Everything is GEODETIC, not GEOCENTRIC, because that's what MSISf expects.
		#Some of these values will be overwritten
		#since at least one must be on a plot axes if line plot,
		#or at least two if a colored plot (pcolor or contour)
		self.mr.nextrun.vars['Latitude'] = float(self.controlstate['lat'])
		self.mr.nextrun.vars['Longitude'] = float(self.controlstate['lon'])
		self.mr.nextrun.vars['Altitude'] = float(self.controlstate['alt'])

		#Copy out the drivers from the controlstate (only copy those that are exposed via the model's __init__)
		self.mr.nextrun.drivers['dt'] = self.controlstate['drivers']['dt']

		#Now we determine from the plottype if we need to grid x and y
		
		if self.plotProperty('gridxy'):
			#Fault checks
			if not self.is_position('x'): #vars dict starts only with position and time
				raise RuntimeError('xvar %s is not a valid position variable!' % (self.controlstate['xvar']))
			else:
				#self.mr.nextrun.lims[self.controlstate['xvar']] = self.controlstate['xbounds']
				self.mr.nextrun.npts[self.controlstate['xvar']] = self.controlstate['xnpts']
				self.mr.nextrun.set_x(self.controlstate['xvar'])

			if not self.is_position('y'):
				raise RuntimeError('yvar %s is not a valid position variable!' % (self.controlstate['yvar']))
			else:
				#self.mr.nextrun.lims[self.controlstate['yvar']] = self.controlstate['ybounds']
				self.mr.nextrun.npts[self.controlstate['yvar']] = self.controlstate['ynpts']
				self.mr.nextrun.set_y(self.controlstate['yvar'])
			
		else: #We do not need to grid data
			#Check that at least one selected variable is a location
			#Handle multiple variables on an axis
			if self.is_multi('x') and self.is_position('x'):
				self.controlstate['xvar']=self.controlstate['xvar'][0]
				raise RuntimeError('Multiple plotting of position variables is not allowed!')

			elif self.is_multi('y') and self.is_position('y'):
				self.controlstate['yvar']=self.controlstate['yvar'][0]
				raise RuntimeError('Multiple plotting of position variables is not allowed!')
				
			elif not self.is_position('x') and not self.is_position('y'):
				raise RuntimeError('%s and %s are both not valid position variables!' % (self.controlstate['xvar'],self.controlstate['yvar']))
			
			elif not self.is_multi('x') and self.is_position('x'): #It's scalar, so check if it's a position
				#self.mr.nextrun.lims[self.controlstate['xvar']] = self.controlstate['xbounds']
				self.mr.nextrun.npts[self.controlstate['xvar']] = self.controlstate['xnpts']
				self.mr.nextrun.set_x(self.controlstate['xvar'])

			elif not self.is_multi('y') and self.is_position('y'): #It's scalar, so check if it's a position
				#self.mr.nextrun.lims[self.controlstate['yvar']] = self.controlstate['ybounds']
				self.mr.nextrun.npts[self.controlstate['yvar']] = self.controlstate['ynpts']
				self.mr.nextrun.set_y(self.controlstate['yvar'])
			else:
				raise RuntimeError('Nonsensical variables: xvar:%s\n yvar:%s\n' % (repr(self.controlstate['xvar']),repr(self.controlstate['yvar'])))

	def make_caption(self):
		"""
		Writes a caption to go with the latest graph
		"""
		#Build a description of the plot
		return self.pdh.caption()+'|'+str(self.mr.runs[-1])

		

	def refresh(self,force_full_refresh=False, force_autoscale=False):
		"""
		Redraws what is on the plot. Trigged on 'refreshnow' POST request.
		This is the big method of this class. 

		The basic outline is that check what controlstate values have changed
		since the last time it was called, and determines based on that
		how to tell the PlotDataHandler how to plot the users desired image.

		Does not neccessarily create a new model run. Tries to determine if
		one is needed by the controlstate differences since last referesh.

		"""
		ffr = force_full_refresh
		fauto = force_autoscale		

		if self.controlstate.changed('plottype') or ffr:
			#Determine if we need to rerun the model
			oldplottype = self.pdh.plottypes[self.pdh.plottype]
			newplottype = self.pdh.plottypes[self.controlstate['plottype']]
			if oldplottype['gridxy'] != newplottype['gridxy']: #we are going from vectors to grids or visa-versa
				self.controlstate['run_model_on_refresh']=True #Must force re-run
			self.pdh.plottype=self.controlstate['plottype']
			
		if self.controlstate.changed('datetime') or ffr:
			#Force model rerun
			self.controlstate['run_model_on_refresh']=True
			self.mr.nextrun.drivers['dt'] = datetime.datetime(**self.controlstate['datetime'])

		if self.controlstate.changed('lat') or ffr:
			if 'Latitude' not in [self.controlstate['xvar'],self.controlstate['yvar']]:
				self.mr.nextrun.hold_constant('Latitude')
				#We are holding latitude constant, so we will have to rerun the model
				self.controlstate['run_model_on_refresh'] = True
		
		if self.controlstate.changed('lon') or ffr:
			if 'Longitude' not in [self.controlstate['xvar'],self.controlstate['yvar']]:
				self.mr.nextrun.hold_constant('Longitude')
				#We are holding longitude constant, so we will have to rerun the model
				self.controlstate['run_model_on_refresh'] = True

		if self.controlstate.changed('alt') or ffr:
			if 'Altitude' not in [self.controlstate['xvar'],self.controlstate['yvar']]:
				self.mr.nextrun.hold_constant('Altitude')
				#We are holding altitude constant, so we will have to rerun the model
				self.controlstate['run_model_on_refresh'] = True
		
		if self.controlstate.changed('differencemode'):
			self.controlstate['run_model_on_refresh'] = True

		if self.controlstate['run_model_on_refresh'] or ffr:
			self.prepare_model_run()
			self.mr.nextrun.populate() #Trigger next model run
			self.mr() #Trigger storing just created model run as mr.runs[-1]
			self.refreshModelRunOptions() #Reset the plotDataHandler, make sure all controlstate options that change with model run are set
			
		#Always grab the most current data	
		xdata,xlims = self.mr[self.controlstate['xvar']] #returns data,lims
		ydata,ylims = self.mr[self.controlstate['yvar']] #returns data,lims
		zdata,zlims = self.mr[self.controlstate['zvar']] #returns data,lims
		
		#print '%s:%s' % (self.controlstate['xvar'],repr(xlims))
		#print '%s:%s' % (self.controlstate['yvar'],repr(ylims))
		#print '%s:%s' % (self.controlstate['zvar'],repr(zlims))
		
		#Reset the bounds, multiplotting and turn of log scaling if we have changed any variables or switched on or off of difference mode
		if self.controlstate.changed('xvar') or self.controlstate.changed('yvar') or \
			 self.controlstate.changed('zvar') or self.controlstate.changed('differencemode') or \
			 self.controlstate.changed('alt') or self.controlstate.changed('lat') or self.controlstate.changed('lon') or ffr:
			self.controlstate['xbounds'] = xlims
			self.controlstate['ybounds'] = ylims
			self.controlstate['zbounds'] = zlims
			#self.controlstate['xlog']=False
			#self.controlstate['ylog']=False
			#self.controlstate['zlog']=False
			#self.controlstate['xmulti']=False
			#self.controlstate['ymulti']=False

		if fauto: 
			self.controlstate['xbounds'] = xlims
			self.controlstate['ybounds'] = ylims
			self.controlstate['zbounds'] = zlims
			
		#Associate data in the data handler based on what variables are desired
		if self.controlstate.changed('xvar') or self.controlstate.changed('xbounds') or self.controlstate.changed('xlog') or self.controlstate['run_model_on_refresh'] or ffr: 
			xname = self.controlstate['xvar']
			self.pdh.associate_data('x',xdata,xname,self.controlstate['xbounds'],self.controlstate['xlog'],multi=self.controlstate['xmulti'])
			
		if self.controlstate.changed('yvar') or self.controlstate.changed('ybounds') or self.controlstate.changed('ylog') or self.controlstate['run_model_on_refresh'] or ffr: 
			yname = self.controlstate['yvar']
			self.pdh.associate_data('y',ydata,yname,self.controlstate['ybounds'],self.controlstate['ylog'],multi=self.controlstate['ymulti'])
			
		if self.controlstate.changed('zvar') or self.controlstate.changed('zbounds') or self.controlstate.changed('zlog') or self.controlstate['run_model_on_refresh'] or ffr:
			zname = self.controlstate['zvar']
			self.pdh.associate_data('z',zdata,zname,self.controlstate['zbounds'],self.controlstate['zlog'])

		#Actually make the plot
		self.pdh.plot()	
		self.caption = self.make_caption()

		#Update the lastcontrolstate 
		self.controlstate.updatelast() 

		#Update the control state xvar_options and drivers
		self.refreshSelectOptions()
		self.refreshModelRunOptions()


	def apply_lipstick(self):
		"""Called on each replot, allows cosmetic adjustment"""
		#self.fig.subplots_adjust(left=0.05,bottom=0.05,top=.95,right=.95)
		fs = 12
		w = .5
		lw = .3
		lp = 0
		pd = .5
		if self.pdh.plottype=='pcolor':
			

			mpl.artist.setp(self.ax.get_xmajorticklabels(),size=fs,rotation=30)
			mpl.artist.setp(self.ax.get_ymajorticklabels(),size=fs)
			mpl.artist.setp(self.pdh.cb.ax.get_xmajorticklabels(),size=fs,rotation=45)
						
			#Label is a text object
			self.ax.xaxis.label.set_fontsize(fs)
			self.ax.yaxis.label.set_fontsize(fs)
			self.ax.xaxis.labelpad=lp
			self.ax.yaxis.labelpad=lp
			
			self.ax.title.set_fontsize(fs)
			self.ax.title.set_fontweight('bold')
			
			#Adjust tick size
			self.ax.xaxis.set_tick_params(width=w,pad=pd)
			self.ax.yaxis.set_tick_params(width=w,pad=pd)

			#Colorbar Ticks
			self.pdh.cb.ax.xaxis.set_tick_params(width=w,pad=pd+.5)
			self.pdh.cb.ax.yaxis.set_tick_params(width=w,pad=pd+.5)
			self.pdh.cb.outline.set_linewidth(w)

			self.ax.grid(True,linewidth=.1)
			#Adjust axes border size
			for axis in ['top','bottom','left','right']:
				self.ax.spines[axis].set_linewidth(lw)
				#self.pdh.cb.spines[axis].set_linewidth(lw)
					
		elif self.pdh.plottype=='map':
			#Colorbar Ticks
			
			mpl.artist.setp(self.pdh.cb.ax.get_xmajorticklabels(),size=fs,rotation=45)
			self.pdh.cb.ax.xaxis.set_tick_params(width=w,pad=pd+.5)
			self.pdh.cb.ax.yaxis.set_tick_params(width=w,pad=pd+.5)
			self.pdh.cb.outline.set_linewidth(w)
						#Adjust axes border size
			for axis in ['top','bottom','left','right']:
				self.ax.spines[axis].set_linewidth(lw)


class AtModWebObj(object):
	def __init__(self):
		self.rootdir = '/home/liamk/mirror/Projects/satdraglab/AtModWeb'
		self.imgreldir = 'www'
		self.docreldir = 'docs'
		self.uihandler = UiHandler(self)
		self.controlstate = self.uihandler.controlstate
		self.canvas = FakeCanvas(self,self.controlstate)
		self.canvas.refresh(force_full_refresh=True)
		self.replot()

	def replot(self):
		#self.canvas.refresh(force_full_refresh=True)
		#Name file with unix epoch
		relfn = os.path.join(self.imgreldir,'session_file_%d.png' % (int(time.mktime(datetime.datetime.now().timetuple()))))
		absfn = os.path.join(self.rootdir,relfn)
		self.canvas.fig.savefig(absfn,dpi=250)
		#Generate caption
		cap = self.canvas.caption
		self.controlstate['lastcaption']=cap
		self.controlstate['recentcaptions'].append(cap)
		self.controlstate['lastplot']=relfn
		self.controlstate['recentplots'].append(relfn)
		#Deal with the plot and caption history
		if len(self.controlstate['recentplots']) > 10:
			tobedeleted = self.controlstate['recentplots'].pop(0)
			oldcap = self.controlstate['recentcaptions'].pop(0)
			os.remove(os.path.join(self.rootdir,tobedeleted))
			logging.info("REMOVED old plot %s" % (tobedeleted))

		logging.info('Replotted to %s\n' % (absfn))
		return relfn, cap


if __name__ == '__main__':
	

	

	webapp = AtModWebObj()
	conf = {
		 '/': {
			'tools.sessions.on': True,
			#'tools.sessions.storage_type':"memcached",
			'tools.sessions.locking':'implicit'
		 },
		 '/index.html': {
			'tools.staticfile.on':True,
			'tools.staticfile.filename': os.path.join(os.path.abspath(webapp.rootdir),'www','atmodweb.html')
		 },
		 '/uihandler': {
			 'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
			 'tools.response_headers.on': True,
			 'tools.response_headers.headers': [('Content-Type', 'application/json')],
		 },
		 '/www': {
			 'tools.staticdir.on': True,
			 'tools.staticdir.dir': os.path.join(os.path.abspath(webapp.rootdir),'www')
		 },
		 '/docs': {
			 'tools.staticdir.on': True,
			 'tools.staticdir.dir': os.path.join(os.path.abspath(webapp.rootdir),'doc/build/html')
		 },
		 '/favicon.ico': {
			'tools.staticfile.on':True,
			'tools.staticfile.filename':os.path.join(os.path.abspath(webapp.rootdir),"www","favicon.ico")
		 }
	 }

	#Optional password protection by setting some environent variables
	if 'CHERRYPY_USER' in os.environ and 'CHERRYPY_PWD' in os.environ:
		USERS = {os.environ['CHERRYPY_USER']:os.environ['CHERRYPY_PWD']}
		conf['/']['tools.auth_digest.on']=True
		conf['/']['tools.auth_digest.realm']='localhost'
		conf['/']['tools.auth_digest.get_ha1']=auth_digest.get_ha1_dict_plain(USERS)
		conf['/']['tools.auth_digest.key']='b565d27146791cfc'
	    
	cherrypy.config.update({'server.socket_host':os.getenv('CHERRYPY_IP'),'server.socket_port': 8080})
  
	cherrypy.quickstart(webapp, '/',conf)
