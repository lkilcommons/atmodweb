import cherrypy #Python web server
#Main imports
import numpy as np
import sys, pdb, textwrap, datetime,os,time, glob, traceback, time, shutil, subprocess, gc
import socket #to figure out our hostname
import matplotlib as mpl
mpl.use('Agg')
import matplotlib.pyplot as pp

from mpl_toolkits.basemap import Basemap
from matplotlib import ticker
from matplotlib.colors import LogNorm, Normalize
from collections import OrderedDict
import random
import logging
logging.basicConfig(level=logging.DEBUG)

from cherrypy.lib import auth_digest
from cherrypy._cpdispatch import Dispatcher
import copy #Dicts must be deepcopied.

#Import the model running code
from atmodexplorer.atmodbackend import ModelRunner, MsisRun, ModelRun, PlotDataHandler

# create logger 
log = logging.getLogger('atmodweb_root')
log.setLevel(logging.DEBUG)
# create file handler which logs everything except debug messages
#fh = logging.FileHandler('atmodweb_root_%s.log' % (datetime.datetime.now().strftime("%c")))
#fh.setLevel(logging.INFO)

# create console handler with a lower log level
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#fh.setFormatter(formatter)
ch.setFormatter(formatter)

# add the handlers to the logger
#log.addHandler(fh)
log.addHandler(ch)

def strongly_expire(func):
    """Decorator that sends headers that instruct browsers and proxies not to cache.
    """
    def newfunc(*args, **kwargs):
        cherrypy.response.headers['Expires'] = 'Sun, 19 Nov 1978 05:00:00 GMT'
        cherrypy.response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0'
        cherrypy.response.headers['Pragma'] = 'no-cache' 
        return func(*args, **kwargs)
    return newfunc

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
		self.log = logging.getLogger(self.__class__.__name__)
		
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
		self.log.debug("Now pushing controlstate contents to cherrypy.session")
		for key in self:
			if cherrypy.session.has_key(key):
				logging.warn('Overwriting already-existing key %s in session.' % (key))
			cherrypy.session[key] = dict.__getitem__(self,key)


	def sanized_set(self,key,new_val,subkey=None):
		"""
		Examines a new value that is going to be put into the controlstate to see if it passes
		basic sanity checks, like being the same type as the old value, and, if it's a list,
		having the same number of elements, or if a dict, having the same keys
		"""
		if subkey is None:
			oldval = dict.__getitem__(self,key)
		else:
			olddict = dict.__getitem__(self,key)
			oldval = olddict[key]

		if isinstance(oldval,list):
			if not isinstance(newval,list):
				self.log.debug("At key %s, attempted to replace %s with %s, which is not a list!" % (str(oldval),str(newval)))
				return False

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
			item = dict.__getitem__(self,key)
			if hasattr(item,'__deepcopy__'): #Make sure that we're not getting references
				newitem = item.deepcopy()
			elif hasattr(item,'__copy__') or isinstance(item,dict):
				newitem = copy.deepcopy(item)
			else:
				newitem = item
			newdict[key] = newitem 

		return newdict	

class ControlStateManager(object):
	"""
	Contains and manages controlstate objects
	Since controlstates and the model runs they create are intrinsically linked,
	this class is a 'peer' of ModelRunner. What that means in practice is that
	ControlStateManager.states and ModelRunner.runs should be 1 to 1, i.e. the n-th
	index of ModelRunner.runs should be the model run created by the n-th index of ControlStateManager.states
	"""
	def __init__(self):
		self.log = logging.getLogger(self.__class__.__name__)
		
		self.states = [] #List of controlstates
		self.default_controlstate = {'model_index':-1,'datetime':{'year':2000,'month':6,'day':21,'hour':12,'minute':0,'second':0},\
			'lat':40.0274,'lon':105.2519,'alt':200.,\
			'plottype':'map',\
			'descstr':'intial plot','gif_mode':False,\
			'xvar':'Longitude','xbounds':[-180.,180.],'xnpts':50.,'xlog':False,'xmulti':False,'xunits':'deg','xdesc':'Longitude',\
			'yvar':'Latitude','ybounds':[-90.,90.],'ynpts':50.,'ylog':False,'ymulti':False,'yunits':'deg','ydesc':'Geodetic Latitude',\
			'zvar':'Temperature','zbounds':[0.,1000.],'zlog':False,'zmulti':False,'zunits':'K','zdesc':'Atmospheric Temperature',\
			'modelname':'msis','differencemode':False,'run_model_on_refresh':True,'controlstate_is_sane':None,
			'thisplot':None,'thiscaption':None,'mapproj':'moll',
			'drivers':{'dt':datetime.datetime(2000,6,21,12,0,0)},
			'drivers_units':{'dt':None},
			'drivers_ranges':{'dt':[datetime.datetime(1970,1,1),datetime.datetime(2012,12,31,23,59,59)]},
			'drivers_descriptions':{'dt':'date and time of model run'},
			'driver_lookup':True}

		self._bound_meth = dict() # Methods which are bound to certain controlstate keys, such that when those keys are changed,
								  #the methods are called. Sort of an ad-hoc slots and signals a'la QT
		self.errors = [] #If the Synchronizer produces an error during refresh, it will pass a message to controlstatemangager
						#to tell it the controlstate is bad
		self.controlstate = None
		self.special_keys = ['lasterror'] #Keys that can be 'get'ed or 'set' which aren't in the current controlstate
										#They all get some individual ControlState instance independant variable
										#'lasterror' gets self.errors[-1], and is a way for the front end to get an
										#error message that was created with self.error
		self.n_max_states = 10.
		self.n_total_states = 0.
		self._lastind = -1

		#Add our first controlstate
		self.set_default_state()


	@property
	def lastind(self):
		return self._lastind

	@lastind.setter
	def lastind(self, value):
		value = int(value)
		if value >= 0:
			self.log.warn("Attempted to set control state history index to %s, Only negative indicies allowed!" % ( str(value) ))
			value = -1
		elif value < -1*len(self.states):
			self.log.warn("Attempted to set control state history index to %s, but only %s plots in history!" % ( str(value),str(len(self.states))))
			value = -1*len(self.states)
		self._lastind = value
		self.restore(self.lastind) #Restore that controlstate
		
	def __contains__(self, key):
		"""Make sure we can use 'in' with this, by passing all in calls through to the current controlstate, or,
		if it's an exception key which has special behaviour when used in getting and setting, it will be in self.special_keys"""
		if key not in self.special_keys:
			return key in self.controlstate
		else:
			return True 
			
	def __call__(self):
		#If we've gotten here, it's because we successfully refreshed, so this is an okay set of controlstate settings
		self.controlstate['controlstate_is_sane']=True
		self._lastind = -1 # Fix it so that the previous and next are always referenced to the plot that is displaying (i.e
			#If we've gotten here then we've just plotted something, and this controlstate is getting appended to self.states,
			#so the previous plot should be at -2, one before this one)
		
		#Add to the history on call

		self.n_total_states += 1
		self.log.debug("Now adding controlstate %d to history." %(self.n_total_states))
		self.log.debug("--Drivers dictionary is %s" %(str(self.controlstate['drivers'])))
		if len(self.states) > 0:
			changeddict = self.changed()
			for key in changeddict:
				self.log.debug("--Key %s changed from self.states[-1]\n %s \nto current\n %s" % (key,str(self.states[-1][key]),str(self.controlstate[key])))
		self.states.append(self.controlstate.copyasdict())

		if len(self.states)>self.n_max_states:
			del self.states[0]
			self.log.info( "Exceeded total number of stored controlstates %d. Removed %dth controlstate." %(self.n_max_states,self.n_total_states))

	def __setitem__(self, key, value):
		"""Setting on the ControlStateManager sets on the current ControlState and triggers bound methods"""
		if key not in self.special_keys:
			self.controlstate[key] = value
		if key in self._bound_meth:
			for meth in self._bound_meth[key]:
				self.log.debug("ControlStateManager TRIGGERING BOUND METHOD %s of key %s new value %s" % (meth.__name__,str(key),str(self[key])))
				meth()
		
	def __getitem__(self, key):
		"""Getting on the ControlStateManager gets on the current ControlState, unless the key is 'lasterror' in which case it gets the last bad controlstate"""
		if key not in self.special_keys:
			return self.controlstate[key]
		elif key == 'lasterror': #Extra behaviors
			if len(self.errors) > 0:
				self.log.info("Returning error %s to controlstate caller" % (self.errors[-1]))
				return self.errors[-1]
			else:
				return "No Error"
		
	def set_default_state(self):
		# change the working ControlState to the default one  
		self.controlstate = ControlState() # Overwrite anything already there
		#Fill up the controlstate instance
		self.log.debug("Overwriting working controlstate with default values.")
		for key in self.default_controlstate:
			self.controlstate[key]=self.default_controlstate[key]	
		self.controlstate.sync = True

	def changed(self,key=None):
		"""
		Is the current value assigned to key changed since last updatelast call?
		"""
		if key is None and len(self.states)>=1:
			ch = dict()
			for key in self.states[-1]:
				if self.changed(key):
					ch[key]=self.controlstate[key]
			return ch
		elif len(self.states)>=1:
			
			if key in self.states[-1]:
				#Typecheck
				if isinstance(self.controlstate[key],list) and isinstance(self.states[-1][key],list):
					if len(self.controlstate[key]) != len(self.states[-1][key]):
						return False
				if isinstance(self.controlstate[key],dict) != isinstance(self.states[-1][key],dict):
					return False
				try:
					oldeqnew = self.states[-1][key] != self.controlstate[key] 
				except:
					self.log.error("Unable to compare this controlstate key %s with last, because compare statement errored" % (key))
					self.log.error("self.states[-1][%s]=i\n%s\nself.controlstate[%s]=\n%s" % (key,str(self.states[-1][key]),key,str(self.controlstate[key])))
					return False	
				return oldeqnew 
			else:
				self.log.warn("Key %s not in controlstate memory\n" % (key))
				return True
		else:
			self.log.warn("No historical controlstates are available (key %s) \n" % (key))
			return True


	def bind_changed(self,key,meth):
		"""
		Binds a method with no inputs to call when the controlstate item corresponding to key is called
		"""
		if key in self._bound_meth:
			self._bound_meth[key].append(meth)
			self.log.debug("Method %s added to bound methods for key %s" % (meth.__name__,key))
		else:
			self._bound_meth[key] = [meth]
			self.log.debug("Key %s got it's first bound method %s" % (key,meth.__name__))

	def trigger_changed(self,key,**kwargs):
		"""
		Triggers a bound on changed method corresponding to key
		Allows specification of keyword arguments (as oppssed to setting the value, which doens't)
		Specifically this gets used when setting subelements of dictionarys in this dictionary
		because that doesn't trigger a '__set__'
		"""
		self.log.debug("MANUALLY triggering bound methods for key %s" % (key))
		for meth in self._bound_meth[key]:
			meth(**kwargs)	

	def restore(self,ind):
		"""Copies all values from controlstate at states[ind] to current controlstate"""
		self.log.debug("Restoring controlstate from history at index[%d]" % (ind))
		for key in self.states[ind]:
			self.controlstate[key]=self.states[ind][key]
			try:
				if self.controlstate[key] != self.states[ind][key]:
					self.log.debug("--On restore: differing values:\n--current controlstate %s value:\n ---%s \n with self.states[%s][%s], value:\n ---%s" % (key,
					str(self.controlstate[key]),str(ind),str(key),str(self.controlstate[key])))
			except: #This should not be a breaking error
				pass 

	def restore_last_good(self):
		"""
		Tries to find a model run with model_run_success = True and then restores those settings
		to the current controlstate.
		"""
		found = False
		tobedeleted = []
		for i in range(len(self.states)):
			#Work backwards
			ind = -1-i
			if self.states[ind]['controlstate_is_sane']:
				found = True
				self.restore(ind)
				self.log.info("Restoring last controlstate from history for which model run succeeded. Index %d is known good" % (ind))
				break
		#	else:
		#		tobedeleted.append(ind)
		#		self.log.info("Controlstate at index %d was unsuccessful in running model and will be removed from the history" % (ind) )

		#for ind in tobedeleted:
		#	del self.states[ind]

		if not found:
			self.set_default_state()

	def error(self,message,roll_back=True):
		"""This method is called when we want to throw an error back to the front end because something in the control state is incorrect,
		or badly formatted. Stores a custom error message which can be recalled with a GET from the UiHandler/Frontend. The
		roll_back keyword argument, when true, will restore the controlstate to the last known good value"""

		#If we got here, the controlstate settings are bad. We will set the appropriate flag
		self.controlstate['controlstate_is_sane']=False

		#Add the message to the errors list
		self.errors.append(message)

		if roll_back:
			self.restore_last_good()

class Synchronizer(object):
	"""
	Reacts to UiHandler PUT changes in the controlstate via the bound methods
	Also has methods which are called by UiHandler POST
	Prepares Model Runs and Refreshes the FakeCanvas figure via PlotDataHandler
	"""
	def __init__(self,canvas,uihand):
		#mr is the ModelRunner instance
		#csm is the ControlStateManager instance 
		self.log = logging.getLogger(self.__class__.__name__)
		
		self.mr = None #Placeholder for ModelRunner instance
		self.canvas = canvas #The FakeCanvas instance we will plot on
		self.uihand = uihand
		self.controlstate =  self.uihand.controlstate #The UI Handler has to spin up the controlstate b
		self.pdh = PlotDataHandler(self.canvas,controlstate=self.controlstate) #PDH needs canvas, obviously since it needs to plot
		self.initModelRunner()
		
		#Bind on changed methods
		self.log.info("Binding execute on change controlstate methods")
		self.controlstate.bind_changed('plottype',self.refreshSelectOptions)
		self.controlstate.bind_changed('xbounds',self.xbounds_changed)
		self.controlstate.bind_changed('ybounds',self.ybounds_changed)
		self.controlstate.bind_changed('xvar',self.xvar_changed)
		self.controlstate.bind_changed('yvar',self.yvar_changed)
		self.controlstate.bind_changed('zvar',self.zvar_changed)
		self.controlstate.bind_changed('datetime',self.datetime_changed)
		self.controlstate.bind_changed('drivers',self.drivers_changed)
		self.controlstate.bind_changed('mapproj',self.mapproj_changed)
		#self.controlstate.bind_changed('modelname',self.modelname_changed)

	def initModelRunner(self):
		"""Does a first run of the model specified in the controlstate to make sure that there's a reference run. 
		A lot of code looks to the previously run model (i.e. to populate the selects for x, y and z)"""

		if self.mr is None:
			self.mr = ModelRunner(firstmodel=self.controlstate['modelname'])
		else:
			#Don't create a new modelrunner if we changed models, just 
			#use the same one...a heterogeneous collection of ModelRun
			#objects in mr.runs doens't really matter much unless
			#we're trying to use peering, which AtModWeb doesn't
			self.mr.model = self.controlstate['modelname']
			self.mr.init_nextrun()

		#Make sure the default selection is sane and set the appropriate things in the next model run instance
		self.prepare_model_run()

		#Now run the model
		self.mr.nextrun.populate()
		#Append the model run to the runs database
		self.mr()
		
	def refreshModelRunOptions(self):
		"""To be called whenever a new model run is instantiated. Updates all controlstate options which change with model run"""
		#Update the drivers dictionary in
		self.log.info("refreshModelRunOptions called...copying drivers dictionary and clearing plot data handler data")
		self.pdh.clear_data()
		self.log.debug(self.mr.runs[-1].drivers.__class__.__name__+':'+str(self.mr.runs[-1].drivers))
		self.controlstate['drivers']=self.mr.runs[-1].drivers.copyasdict()
		for key in self.controlstate['datetime']:
			self.controlstate['datetime'][key] = getattr(self.mr.runs[-1].drivers['dt'],key)
		self.controlstate['drivers_units']=copy.deepcopy(self.mr.runs[-1].drivers.units)
		self.controlstate['drivers_ranges']=copy.deepcopy(self.mr.runs[-1].drivers.allowed_range)
		self.controlstate['drivers_descriptions']=copy.deepcopy(self.mr.runs[-1].drivers.descriptions)
		

	def autoscale(self):
		"""Updates the xbounds,ybounds and zbounds in the controlstate from the lims dictionary in last model run"""
		self.mr.runs[-1].autoscale_all_lims() #Sets all lims to their min and max in the model data

		xdata,xlims,xunits,xdesc = self.mr[self.controlstate['xvar']] #returns data,lims
		ydata,ylims,yunits,ydesc = self.mr[self.controlstate['yvar']] #returns data,lims
		zdata,zlims,zunits,zdesc = self.mr[self.controlstate['zvar']] #returns data,lims

		self.controlstate['xbounds']=xlims
		self.controlstate['ybounds']=ylims
		self.controlstate['zbounds']=zlims

	def drivers_changed(self,subfield=None):
		"""On changed to controlstate['drivers'], update the next model run drivers"""
		#Currently done in referesh?
		if subfield is None:
			#Nothing calls this without a subfield right now
			#Do Nothing
			pass
		else:
			old_driver_val = str(self.mr.nextrun.drivers[subfield]) if subfield in self.mr.nextrun.drivers else "no previous value"
			self.log.debug("drivers_changed: next model run driver %s changed from %s to %s" % (subfield,old_driver_val,
				str(self.controlstate['drivers'][subfield])))
			self.mr.nextrun.drivers[subfield] = self.controlstate['drivers'][subfield]
			if subfield == 'dt':
				for f in self.controlstate['datetime']:
					self.controlstate['datetime'][f] = getattr(self.controlstate['drivers']['dt'],f)

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
		xdata,xlims,xunits,xdesc = self.mr[self.controlstate['xvar']] #returns data,lims, works for multi
		self.controlstate['xbounds']=xlims
		self.controlstate['xunits']=xunits
		self.controlstate['xdesc']=xdesc

	def yvar_changed(self):
		"""Updates the ybounds in the controlstate when a new yvar is selected"""
		ydata,ylims,yunits,ydesc = self.mr[self.controlstate['yvar']] #returns data,lims, works for multi
		self.controlstate['ybounds']=ylims
		self.controlstate['yunits']=yunits
		self.controlstate['ydesc']=ydesc

	def zvar_changed(self):
		"""Updates the zbounds in the controlstate when a new zvar is selected"""
		zdata,zlims,zunits,zdesc = self.mr[self.controlstate['zvar']] #returns data,lims, works for multi
		self.controlstate['zbounds']=zlims
		self.controlstate['zunits']=zunits
		self.controlstate['zdesc']=zdesc

	def xbounds_changed(self):
		"""Function which is called whenever the xbounds are changed in the controlstate. Changes limits for next model run"""
		if not self.is_multi('x') and self.is_position('x'): 
			self.mr.nextrun.vars.lims[self.controlstate['xvar']] = self.controlstate['xbounds']
		elif self.is_multi('x') and not isinstance(self.controlstate['xbounds'][0],list):
			nvars = len(self.controlstate['xvar'])
			newlst = []
			for k in range(nvars):
				newlst.append(self.controlstate['xbounds'])
			self.controlstate['xbounds'] = newlst

	def ybounds_changed(self):
		"""Function which is called whenever the ybounds are changed in the controlstate. Changes limits for next model run"""
		if not self.is_multi('y') and self.is_position('y'): 
			self.mr.nextrun.vars.lims[self.controlstate['yvar']] = self.controlstate['ybounds']
		elif self.is_multi('y') and not isinstance(self.controlstate['ybounds'][0],list):
			nvars = len(self.controlstate['yvar'])
			newlst = []
			for k in range(nvars):
				newlst.append(self.controlstate['ybounds'])
			self.controlstate['ybounds'] = newlst
			
	def mapproj_changed(self):
		"""Map projection type changed"""
		if self.controlstate['mapproj'] in self.pdh.supported_projections:
			self.pdh.mapproj = self.controlstate['mapproj']

	#def modelname_changed(self):
	#	"""Model name is changed, big reinit"""
	#	if self.controlstate['modelname'] in ['msis','iri']:
	#		self.initModelRunner()
	#		self.refreshSelectOptions()
	#		self.refreshModelRunOptions()

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
		for k in self.mr.runs[-1].vars:
			all_options_dict[k]=k

		for var in ['x','y','z']:
			options_dict = dict()
			#Short circuting options
			if 'all' in allowed[var]:
				options_dict=copy.deepcopy(all_options_dict)	
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
		
		Also tells that ModelRun which position variables will be constant,
		and which independant: i.e. if we are plotting a 'Temperature'
		vs. 'Altitude' plot, then we want to determine which latitude
		and longitude values the user wants the model to calculate the altitude profile
		for from the controlstate (and lat and lon will be constant for the model run).

		"""
	
		#Begin by assigning all of the position variables their approprate output
		#from the controls structure. These are all single (scalar) values set by
		#the frontend HTML elements for Lat, Lon and Alt.
		#Everything is GEODETIC, not GEOCENTRIC, because that's what MSIS expects.
		#Some of these position variables will be ignored
		#since one must be on a plot axes if line plot,
		#or two if a colored plot (pcolor or map)
		#These values will be the values for their associated
		#position variable if it is not one of the axes of the plot 
		self.mr.nextrun.vars['Latitude'] = self.controlstate['lat']
		self.mr.nextrun.vars['Longitude'] = self.controlstate['lon']
		self.mr.nextrun.vars['Altitude'] = self.controlstate['alt']

		#Handle the case of two variables being set to the same thing:
		if self.controlstate['xvar'] == self.controlstate['yvar']:
			raise RuntimeError('X and Y both are %s, cannot make sensible plot!' % (self.controlstate['xvar']))
		
		#Make sure all position variables have their limits set correctly
		#before model run so that we end up with the right generated 
		#grid 
		if not self.is_multi('x') and self.is_position('x'): 
				self.mr.nextrun.vars.lims[self.controlstate['xvar']] = self.controlstate['xbounds']
		if not self.is_multi('y') and self.is_position('y'): 
				self.mr.nextrun.vars.lims[self.controlstate['yvar']] = self.controlstate['ybounds']

		#Copy out the drivers from the controlstate (only copy those that are exposed via the model's __init__)
		self.mr.nextrun.drivers['dt'] = self.controlstate['drivers']['dt']

		#Now we determine from the plottype if we need to grid x and y
		if self.plotProperty('gridxy'):
			#Fault checks
			if not self.is_position('x'): #vars dict starts only with position and time
				raise RuntimeError('xvar %s is not a valid position variable!' % (self.controlstate['xvar']))
			else:
				#self.mr.nextrun.lims[self.controlstate['xvar']] = self.controlstate['xbounds']
				self.mr.nextrun.vars.npts[self.controlstate['xvar']] = self.controlstate['xnpts']
				self.mr.nextrun.set_x(self.controlstate['xvar'])

			if not self.is_position('y'):
				raise RuntimeError('yvar %s is not a valid position variable!' % (self.controlstate['yvar']))
			else:
				#self.mr.nextrun.lims[self.controlstate['yvar']] = self.controlstate['ybounds']
				self.mr.nextrun.vars.npts[self.controlstate['yvar']] = self.controlstate['ynpts']
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
				raise RuntimeError('%s and %s are both not valid position variables!' % (str(self.controlstate['xvar']),str(self.controlstate['yvar'])))
			
			elif not self.is_multi('x') and self.is_position('x'): #It's scalar, so check if it's a position
				#self.mr.nextrun.lims[self.controlstate['xvar']] = self.controlstate['xbounds']
				self.mr.nextrun.vars.npts[self.controlstate['xvar']] = self.controlstate['xnpts']
				self.mr.nextrun.set_x(self.controlstate['xvar'])

			elif not self.is_multi('y') and self.is_position('y'): #It's scalar, so check if it's a position
				#self.mr.nextrun.lims[self.controlstate['yvar']] = self.controlstate['ybounds']
				self.mr.nextrun.vars.npts[self.controlstate['yvar']] = self.controlstate['ynpts']
				self.mr.nextrun.set_y(self.controlstate['yvar'])
			else:
				raise RuntimeError('Nonsensical variables: xvar:%s\n yvar:%s\n' % (repr(self.controlstate['xvar']),repr(self.controlstate['yvar'])))

	def refresh(self,force_full_refresh=False, force_autoscale=False):
		"""
		Redraws what is on the plot. Trigged on 'refreshnow' POST request.
		This is the big method of this class. 

		The basic outline is that check what controlstate values have changed
		since the last time it was called, and determines based on that
		how to tell the PlotDataHandler how to plot the user's desired image.

		Does not neccessarily create a new model run. Tries to determine if
		one is needed by the controlstate differences since last referesh.
		"""
		ffr = force_full_refresh
		fauto = force_autoscale		

		#if self.controlstate['plottype'] == 'pcolor' and self.controlstate.changed("xvar") or self.controlstate.changed("yvar"):
		#	self.controlstate['run_model_on_refresh']=True
		#	self.log.info("We are plotting a pcolor type plot, and x or y was changed, so we will need to re-run the model, since what is held constant has changed")

		if self.controlstate.changed('plottype') or ffr:
			#Determine if we need to rerun the model
			oldplottype = self.pdh.plottypes[self.pdh.plottype]
			newplottype = self.pdh.plottypes[self.controlstate['plottype']]
			self.log.info("Plottype was changed since last refresh, from %s to %s." % (oldplottype,newplottype))
			if oldplottype['gridxy'] != newplottype['gridxy']: #we are going from vectors to grids or visa-versa
				self.controlstate['run_model_on_refresh']=True #Must force re-run
				self.log.info("This change requires a %s re-run, since gridding scheme has changed" % (self.controlstate['modelname']))
			self.pdh.plottype=self.controlstate['plottype']
			self.refreshSelectOptions()
			
		if self.controlstate.changed('datetime') or self.controlstate.changed('drivers') or ffr:
			#Force model rerun
			self.controlstate['run_model_on_refresh']=True
			try:
				self.mr.nextrun.drivers['dt'] = datetime.datetime(**self.controlstate['datetime'])

			except:
				#Capture the error for retrieval by the frontend failure callback
				self.log.error("Badly formed time! Calling controlstate error function")
				self.log.error( traceback.format_exc() )
				self.controlstate.error("Badly formed time!: "+str(sys.exc_info()))
				self.controlstate.restore_last_good()
				raise #continue erroring

			self.log.info("Datetime was changed since last refresh. Will rerun %s with datetime %s" % (self.controlstate['modelname'],
				self.mr.nextrun.drivers['dt'].strftime('%c')))

		if self.controlstate.changed('lat') or ffr:
			if 'Latitude' not in [self.controlstate['xvar'],self.controlstate['yvar']]:
				self.log.info("Now holding Latiude constant")
				self.mr.nextrun.hold_constant('Latitude')
				#We are holding latitude constant, so we will have to rerun the model
				self.controlstate['run_model_on_refresh'] = True
		
		if self.controlstate.changed('lon') or ffr:
			if 'Longitude' not in [self.controlstate['xvar'],self.controlstate['yvar']]:
				self.log.info("Now holding Longitude constant")
				self.mr.nextrun.hold_constant('Longitude')
				#We are holding longitude constant, so we will have to rerun the model
				self.controlstate['run_model_on_refresh'] = True

		if self.controlstate.changed('alt') or ffr:
			if 'Altitude' not in [self.controlstate['xvar'],self.controlstate['yvar']]:
				self.log.info("Now holding Altitude constant")
				self.mr.nextrun.hold_constant('Altitude')
				#We are holding altitude constant, so we will have to rerun the model
				self.controlstate['run_model_on_refresh'] = True
		
		#If position boundaries were changed
		if any([self.is_position(coord) and self.controlstate.changed(coord+'bounds') for coord in ['x','y']]):
			self.log.info("Position boundaries changed, will rerun model")
			self.controlstate['run_model_on_refresh'] = True

		if self.controlstate.changed('differencemode'):
			self.controlstate['run_model_on_refresh'] = True

		#---------------------------------------------------------------------------------------------------------------------------------------
		#Actually prepare for a new run of the model
		if self.controlstate['run_model_on_refresh'] or ffr:
			self.log.info("Now preparing next model run, because controlstate variable run_model_on_refresh==True")
	
			try: #Attempt to run the model
				self.prepare_model_run()
			except RuntimeError as e: #Prepare model run can throw quite a few possible runtime errors based on incorrect variables selection
				self.log.error("Model preperation FAILED. Calling controlstate error function")
				self.log.error( traceback.format_exc() )
				self.controlstate.error("Prep for model call FAILED: "+str(e))
				#Continue erroring
				raise 

			#If we succeeded in preparing the model try to actually run it
			try:	
				self.mr.nextrun.populate() #Trigger next model run
			except:
				#Capture the error for retrieval by the frontend failure callback
				self.log.error("Model call FAILED. Calling controlstate error function")
				self.log.error( traceback.format_exc() )
				self.controlstate.error("Model Call FAILED: "+str(sys.exc_info()))
				self.controlstate.restore_last_good()

				#Continue erroring
				raise 

			#Then maybe we will want to not look up drivers and just keep using the same ones
			propagate = False if self.controlstate['driver_lookup'] else True
			self.mr(propagate_drivers=propagate) #Trigger storing just created model run as mr.runs[-1]
			self.refreshModelRunOptions() #Reset the plotDataHandler, make sure all controlstate options that change with model run are set
			self.refreshSelectOptions()
			
		#---------------------------------------------------------------------------------------------------------------------------------------

		if fauto: 
			self.log.info("Autoscaling because forced")
			self.mr.runs[-1].autoscale_all_lims()
			
		#Always grab the most current data	
		self.log.info("Now getting data for X=%s Y=%s and Z=%s via ModelRunner __getitem__" % (self.controlstate['xvar'],
			self.controlstate['yvar'],self.controlstate['zvar']))
		latlims = self.mr.runs[-1].vars.lims['Latitude']
		lonlims = self.mr.runs[-1].vars.lims['Longitude']
		altlims = self.mr.runs[-1].vars.lims['Altitude']
		xdata,xlims,xunits,xdesc = self.mr[self.controlstate['xvar']] #returns data,lims, correctly handles list xvar
		ydata,ylims,yunits,ydesc = self.mr[self.controlstate['yvar']] #returns data,lims, correctly handles list yvar
		zdata,zlims,zunits,zdesc = self.mr[self.controlstate['zvar']] #returns data,lims, correctly handles list zvar
		
		#Reset the bounds, multiplotting and turn of log scaling if we have changed any variables or switched on or off of difference mode
		if self.controlstate.changed('xvar') or self.controlstate.changed('yvar') or \
			 self.controlstate.changed('zvar') or self.controlstate.changed('differencemode') or \
			 self.controlstate.changed('alt') or self.controlstate.changed('lat') or self.controlstate.changed('lon') or ffr:
			
			self.log.info("A variable or position was changed since last refresh")
			
			self.controlstate['xbounds'] = xlims
			self.controlstate['ybounds'] = ylims
			self.controlstate['zbounds'] = zlims
			
			self.controlstate['xunits'] = xunits
			self.controlstate['yunits'] = yunits
			self.controlstate['zunits'] = zunits
			
			self.controlstate['xdesc'] = xdesc
			self.controlstate['ydesc'] = ydesc
			self.controlstate['zdesc'] = zdesc


		#Associate data in the data handler based on what variables are desired
		if self.controlstate.changed('modelname') or self.controlstate.changed('xvar') or self.controlstate.changed('xbounds') or self.controlstate.changed('xlog') or self.controlstate['run_model_on_refresh'] or ffr: 
			xname = self.controlstate['xvar']
			self.log.info("Associating x variable %s with plot data handler bounds %s, log %s" % (str(xname),
							str(self.controlstate['xbounds']),str(self.controlstate['xlog'])))
			self.pdh.associate_data('x',xdata,xname,self.controlstate['xbounds'],self.controlstate['xlog'],
				multi=self.controlstate['xmulti'],units=xunits,description=xdesc)
			
		if self.controlstate.changed('modelname') or self.controlstate.changed('yvar') or self.controlstate.changed('ybounds') or self.controlstate.changed('ylog') or self.controlstate['run_model_on_refresh'] or ffr: 
			yname = self.controlstate['yvar']
			self.log.info("Associating y variable %s with plot data handler bounds %s, log %s" % (str(yname),
							str(self.controlstate['ybounds']),str(self.controlstate['ylog'])))
			self.pdh.associate_data('y',ydata,yname,self.controlstate['ybounds'],self.controlstate['ylog'],
				multi=self.controlstate['ymulti'],units=yunits,description=ydesc)
			
		if self.controlstate.changed('modelname') or self.controlstate.changed('zvar') or self.controlstate.changed('zbounds') or self.controlstate.changed('zlog') or self.controlstate['run_model_on_refresh'] or ffr:
			zname = self.controlstate['zvar']
			self.log.info("Associating z variable %s with plot data handler bounds %s, log %s" % (str(zname),
							str(self.controlstate['zbounds']),str(self.controlstate['zlog'])))
			self.pdh.associate_data('z',zdata,zname,self.controlstate['zbounds'],self.controlstate['zlog'],units=zunits,description=zdesc)

		self.controlstate['descstr']=self.make_descstr()

		#Actually make the plot
		try:
			self.pdh.plot()	
		except: 
			#Capture the error for retrieval by the frontend failure callback
			self.log.error("PlotDataHandler Plotting FAILED. Calling controlstate error function")
			self.log.error( traceback.format_exc() )
			self.controlstate.error("Data plotting FAILED: "+str(sys.exc_info()))
			#Continue erroring
			raise 

		self.caption = self.make_caption()
		#Make the description string showing what changed since the last plot
		
		#Reinitialize the run_on_refresh setting
		self.controlstate['run_model_on_refresh'] = False

	def make_descstr(self):
		"""Makes a string which shows how the this controlstate differs from the previous one"""
		thestr = ''
		thestr += datetime.datetime(**self.controlstate['datetime']).strftime('%m-%d-%Y %H:%M UT')
		thestr += '\n'
		for driver in self.controlstate['drivers']:
			val = self.controlstate['drivers'][driver]
			if not isinstance(val,list) and not isinstance(val,dict) and driver is not 'dt':
				thestr += "%s: %s\n" % (driver,str(self.controlstate['drivers'][driver]))
		held_positionvars = ['Altitude','Latitude','Longitude']
		controlstate_positions = ['alt','lat','lon']
		for coord in ['x','y']:
			if self.is_position(coord):
				i = held_positionvars.index(self.controlstate[coord+'var'])
				held_positionvars.pop(i)
				controlstate_positions.pop(i)
		for i in range(len(held_positionvars)):
			thestr+='%s: %.2f\n' % (held_positionvars[i],self.controlstate[controlstate_positions[i]])
		thestr = thestr[:-1] # remove trailing newline

		return thestr

	def make_caption(self):
		"""
		Writes a caption fully describing the latest graph
		"""
		#Build a description of the plot
		return self.pdh.caption()+'|'+str(self.mr.runs[-1])

	def data_as_csv(self):
		"""
		Render the current plot's data as a CSV string
		"""
		coords = ['x','y'] if self.controlstate['plottype']=='line' else ['x','y','z']
		vs = [self.controlstate[coord+'var'] for coord in coords]
		data,header = self.mr.runs[-1].as_csv(vs)
		return data,header

class UiHandler(object):
	"""
	A class to hold the state of the UI controls and settings.
	The UiHandler processes requests from the browser (i.e. GET, SET, POST)
	
	"""
	#exposed = True
	def __init__(self,amwo):
		self.log = logging.getLogger(self.__class__.__name__)

		self.amwo = amwo #Parent atmodweb object
		self.controlstate = ControlStateManager()

	def output_sanitize(self,indata):
		"""
		Turns output into something serializable
		Cherrypy is pretty good about doing this itself. Basically all I handle right now is datetime
		"""

		if isinstance(indata,dict):
			outdata = copy.deepcopy(indata)
			for k in outdata:
				outdata[k] = self.output_sanitize(outdata[k])
		elif isinstance(indata,list):
			outdata = copy.deepcopy(indata)
			for k in range(len(outdata)):
				outdata[k] = self.output_sanitize(outdata[k])
		elif isinstance(indata,datetime.datetime):
			outdata = indata.strftime('%Y-%m-%d %H:%M:%S')
		else:
			outdata = indata
		return outdata

	#@cherrypy.tools.accept(media='text/plain')
	#@cherrypy.tools.json_out()
	def GET(self, statevar, subfield=None):
		"""
		ReST GET request handler (i.e. browser asks backend for information and backend returns informations) 
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
		#Direct getting from ControlState
		if statevar in self.controlstate and subfield is None:
			retval = self.controlstate[statevar]
			self.log.info('GET for statevar:%s returning %s' % (statevar,str(retval)))
		elif statevar in self.controlstate and subfield is not None:
			if hasattr(self.controlstate[statevar],'__getitem__'): #Must be some kind of dict like thing
				retval = self.controlstate[statevar][subfield]
				self.log.info('GET for statevar:%s, key:%s returning %s' % (statevar,subfield,str(retval)))
			else: #Just try to do the thing UNSAFE
				if hasattr(self.controlstate[statevar],subfield):
					mymeth = getattr(self.controlstate[statevar],subfield)
					retval = mymeth
					self.log.warn("UNSAFE GET Eval %s = self.controlstate[%s].%s()" % (str(retval),statevar,str(subfield)))
		elif statevar == 'modeldesc':
			#Get the description of the last run model
			retval = {'modeldesc':self.mr.runs[-1].modeldesc}
		elif statevar == 'controlstate':
			#Get the controlstate as an html table
			retval=dict()
			for key in self.controlstate:
				if self.controlstate.changed(key):
					retval[key]=self.controlstate.ashtml(key)
		elif statevar == 'vars':
			#Get all of the information about the variables as one package
			retval = dict()
			for prefix in ['x','y','z']:
				for suffix in ['var','bounds','units','desc','log']:
					retval[prefix+suffix] = dict.__getitem__(self.controlstate,prefix+suffix) 
		elif statevar == 'chartdata':
			#Get all the data about the drivers needed for the d3 chart
			retval = dict()
			for driver in self.controlstate['drivers']:
				retval[driver] = dict()
				retval[driver]['data'] = self.controlstate['drivers'][driver]
				#Now loop on all
				for metadata_key in ['drivers_descriptions','drivers_units','drivers_ranges']:
					if driver in self.controlstate[metadata_key]: 	 
						retval[driver][metadata_key.split('_')[-1]]=self.controlstate[metadata_key][driver]
					else:
						retval[driver][metadata_key.split('_')[-1]]=None
			self.log.info("Chartdata is %s" % (str(retval)))
		retjson[statevar]=self.output_sanitize(retval)
		return retjson

	#@cherrypy.tools.accept(media='text/plain')
	#@cherrypy.tools.json_out()
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
			self.log.info(ansicolors.HEADER+'POST for posttype:%s returning %s' % (posttype,str(retval))+ansicolors.ENDC)
			return {posttype:retval}
		elif posttype == 'restart':
			self.log.info(ansicolors.HEADER+"POST for posttype: restart THE BACKEND WILL NOW RESTART" +ansicolors.ENDC)
			self.amwo.restart()
			return {'restart':True}
		elif posttype == 'nextplot':
			self.controlstate.lastind = self.controlstate.lastind + 1 #lastind is a property. the setter will cause the controlstate to re-sync
			self.log.info(ansicolors.HEADER+"POST for posttype: nextplot get plot at index %d" % (self.controlstate.lastind)+ansicolors.ENDC)
			return {'nextplot':True,'plot':self.controlstate['thisplot'],'caption':self.controlstate['thiscaption'],
					'ind':self.controlstate.lastind+len(self.controlstate.states)+1,'maxind':len(self.controlstate.states)}
		elif posttype == 'prevplot':
			self.controlstate.lastind = self.controlstate.lastind - 1 #lastind is a property. the setter will cause the controlstate to re-sync
			self.log.info(ansicolors.HEADER+"POST for posttype: prevplot get plot at index %d" % (self.controlstate.lastind)+ansicolors.ENDC)
			return {'prevplot':True,'plot':self.controlstate['thisplot'],'caption':self.controlstate['thiscaption'],
					'ind':self.controlstate.lastind+len(self.controlstate.states)+1,'maxind':len(self.controlstate.states)}
		elif posttype == 'uiready':
			#Begin syncing the local controlstate with the session
			self.log.info(ansicolors.HEADER+'POST for posttype:%s beginning controlstate sync' % (posttype)+ansicolors.ENDC)
			self.controlstate.controlstate.sync = True
			return {"uiready":True}
		elif posttype == 'refreshnow':
			self.amwo.syncher.refresh()
			self.log.info(ansicolors.HEADER+'POST for posttype:%s successful refresh' % (posttype)+ansicolors.ENDC)
			return {"refresh":True}
		elif posttype == 'replotnow':
			newfn,newcap = self.amwo.replot()
			self.log.info(ansicolors.HEADER+'POST for posttype:%s successful replot: new file=%s ' % (posttype,newfn)+ansicolors.ENDC)
			return {"src":newfn,"cap":newcap}
		elif posttype == 'refreshselect':
			self.amwo.syncher.refreshSelectOptions()
			self.log.info(ansicolors.HEADER+'POST for posttype:%s successful refresh select options' % (posttype)+ansicolors.ENDC)
			return {"refreshselect":True}
		elif posttype == 'autoscale':
			self.amwo.syncher.autoscale()
			self.log.info(ansicolors.HEADER+'POST for posttype:%s successful refresh variable limits' % (posttype)+ansicolors.ENDC)
			return {"autoscale":True}
		elif posttype == 'refreshmodeloptions':
			newfn = self.amwo.canvas.refreshModelRunOptions()
			self.log.info(ansicolors.HEADER+'POST for posttype:%s successful refresh model run options' % (posttype)+ansicolors.ENDC)
			return {"refreshmodeloptions":True}
		elif posttype == 'gifmode':
			self.controlstate['gif_mode'] = False if self.controlstate['gif_mode'] else True
			f = None
			if not self.controlstate['gif_mode']:
				f = self.amwo.make_gif()
			return {"gifmode":self.controlstate['gif_mode'],"file":f} 
		elif posttype == 'debugreinit':
			#This is extreme measures. Expires the CherryPy session and tries to resync it with a good version of the controlstate
			self.log.info("Reinitializing controlstate")
			cherrypy.lib.sessions.expire()
			self.controlstate.restore_last_good()
			self.controlstate.controlstate.sync = True
			self.log.info(ansicolors.HEADER+'POST for posttype:%s successfully reintialized local controlstate' % (posttype)+ansicolors.ENDC)
			return {"debugreinit":True}

	def input_sanitize(self,inval):
		"""
		Sanitize data that came from a browser PUT request. This method handles inputs that are lists (i.e passed as JS arrays),
		and inpus that are dicts (i.e. passed as JS objects)
		It calls input_sanitize_single to process individual values.
		"""
		self.log.debug("Sanitizing %s" % (str(inval)))
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
			self.log.debug("Sanitizing: %s failed to convert %s to datetime\n" % (val,val))
			pass

		return val

	#@cherrypy.tools.json_out()
	#@cherrypy.tools.accept(media='text/plain')
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
			self.log.info(ansicolors.OKBLUE+'PUT request for statevar:%s old value: %s, new value %s, type: %s ' % (str(statevar),
				str(self.controlstate[statevar]),str(newval),str(type(newval)))+ansicolors.ENDC)
			if statevar in self.controlstate:
				self.controlstate[statevar] = newval
			else:
				raise RuntimeError('PUT request with invalid controlstate addressee %s, data: %s' % (str(statevar),str(newval)))
		else: 
			self.log.info(ansicolors.OKBLUE+'PUT request for statevar:%s, subfield:%s, old value %s, new value %s, type: %s ' % (str(statevar),
				str(subfield),str(self.controlstate[statevar][subfield]),str(newval),str(type(newval)))+ansicolors.ENDC)
			if hasattr(self.controlstate[statevar],'__setitem__'): #Must be some kind of dict like thing
				self.controlstate[statevar][subfield] = newval
				#Have to explicitly trigger changed since we aren't explicitly 
				#setting controlstate['drivers'] TODO find a better way
				self.controlstate.trigger_changed(statevar,subfield=subfield)
			elif hasattr(self.controlstate[statevar],subfield):
				myattr = getattr(self.controlstate[statevar],subfield)
				myattr = newval
				self.log.warn("UNSAFE PUT Eval setattr(self.controlstate[%s],%s,%s)" % (statevar,str(subfield),str(newval)))				
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
	It is a matplotlib canvas in the sense that it has one matplotlib figure at self.fig, and an axes at self.ax. But
	otherwise it's just a convenient way of organizing the code and has nothing to do with Matplotlib.
	It's important parameters are the PlotDataHandler instance as self.pdh, and the ControlState instance at self.controlstate
	It's parent, the AtModWebObj that ties the application together is at self.atmo. It shares it's controlstate with the UiHandler,
	which handles requests.
	"""
	def __init__(self,atmo):		
		self.atmo = atmo #"parent" atmodwebobject
		self.fig = pp.figure(figsize=(6,4),dpi=200)
		self.caption = 'caption' # Caption for the figure, created by make_caption 
		self.ax = self.fig.add_subplot(111)
		self.textobj = None

	def apply_lipstick(self):
		"""Called on each replot, allows cosmetic adjustment"""
		#self.fig.subplots_adjust(left=0.05,bottom=0.05,top=.95,right=.95)
		fs = 9
		w = .5
		lw = .3
		lp = 0
		pd = .5
		# if self.atmo.syncher.pdh.plottype=='pcolor':

		# 	mpl.artist.setp(self.ax.get_xmajorticklabels(),size=fs,rotation=30)
		# 	mpl.artist.setp(self.ax.get_ymajorticklabels(),size=fs)
		# 	mpl.artist.setp(self.atmo.syncher.pdh.cb.ax.get_xmajorticklabels(),size=fs,rotation=45)
						
		# 	#Label is a text object
		# 	self.ax.xaxis.label.set_fontsize(fs)
		# 	self.ax.yaxis.label.set_fontsize(fs)
		# 	self.ax.xaxis.labelpad=lp
		# 	self.ax.yaxis.labelpad=lp
			
		# 	#Adjust tick size
		# 	self.ax.xaxis.set_tick_params(width=w,pad=pd)
		# 	self.ax.yaxis.set_tick_params(width=w,pad=pd)

		# 	#Colorbar Ticks
		# 	self.atmo.syncher.pdh.cb.ax.xaxis.set_tick_params(width=w,pad=pd+.5)
		# 	self.atmo.syncher.pdh.cb.ax.xaxis.label.set_fontsize(fs)
		# 	self.atmo.syncher.pdh.cb.ax.yaxis.set_tick_params(width=w,pad=pd+.5)
		# 	self.atmo.syncher.pdh.cb.outline.set_linewidth(w)

		# 	self.ax.grid(True,linewidth=.1)
		# 	#Adjust axes border size
		# 	for axis in ['top','bottom','left','right']:
		# 		self.ax.spines[axis].set_linewidth(lw)
		# 		#self.pdh.cb.spines[axis].set_linewidth(lw)

		# 	self.ax.title.set_fontsize(fs)
		# 	self.ax.title.set_fontweight('bold')
			
		if self.atmo.syncher.pdh.plottype=='map':
			#Colorbar Ticks
			self.ax.title.set_fontsize(fs)
			self.ax.title.set_fontweight('bold')

			mpl.artist.setp(self.atmo.syncher.pdh.cb.ax.get_xmajorticklabels(),size=fs,rotation=35)
			self.atmo.syncher.pdh.cb.ax.xaxis.set_tick_params(width=w,pad=pd)
			self.atmo.syncher.pdh.cb.ax.yaxis.set_tick_params(width=w,pad=pd)
			self.atmo.syncher.pdh.cb.ax.xaxis.label.set_fontsize(fs)
			self.atmo.syncher.pdh.cb.outline.set_linewidth(w)
						#Adjust axes border size
			for axis in ['top','bottom','left','right']:
				self.ax.spines[axis].set_linewidth(lw)

		elif self.atmo.syncher.pdh.plottype=='line':
			self.ax.title.set_fontsize(fs)
			self.ax.title.set_fontweight('bold')
			if self.atmo.syncher.pdh.ax.get_legend() is not None:
				mpl.artist.setp(self.atmo.syncher.pdh.ax.get_legend().get_texts(),size=fs)
			mpl.artist.setp(self.atmo.syncher.pdh.ax.get_xmajorticklabels(),size=fs,rotation=35)
						#Adjust axes border size
			for axis in ['top','bottom','left','right']:
				self.ax.spines[axis].set_linewidth(lw)


	def text(self,*args,**kwargs):
		"""Displays text on the figure in figure coordinates (0,0) is bottom left, (1,1) is top right"""
		if self.textobj is not None:
			self.textobj.remove()
		self.textobj = self.fig.text(*args,**kwargs)

class AtModWebObj(object):
	"""
	The AtModWebObj class is a representation of a single user session of AtModWeb.
	It includes all of the pieces required for a user with the AtModWeb webpage open in their browser
	to generate plots and interact with the data.
	"""
	def __init__(self,parent,userid=None):
		self.log = logging.getLogger(self.__class__.__name__)
		self.parent = parent
		self.userid = userid
		self.time_created = datetime.datetime.now()
		self.last_accessed = datetime.datetime.now()
		self.gif_frames = []
		self.n_max_plots = 20
		self.n_total_plots = 0
		#Start up the rest of the application
		self.uihandler = UiHandler(self)
		self.controlstate = self.uihandler.controlstate
		self.canvas = FakeCanvas(self)
		self.syncher = Synchronizer(self.canvas,self.uihandler)
		self.syncher.refresh(force_full_refresh=True)
		plots = glob.glob(os.path.join(self.parent.rootdir,self.parent.imgreldir,'amwo_%s_*.png' % (str(self.userid))))
		if len(plots) > self.n_max_plots:
			os.remove(plots) #Clean up after yourself on restart
		self.plots =  [] #List of all plots in the img dir
		self.replot()


	def replot(self):
		"""
		The last step in the creation of a new plot to be displayed in the frontend.

		This function, when called, writes the FakeCanvas' matplotlib figure
		to a file on the disk, the name of which is dependent on the current unix time.
		The URL for the file (as a relative path) is then recorded in the controlstate,
		and returned to the caller (usually the UiHandler, which then relays it to the frontend in 
		a HTTP response). 
		Does several other incidental labeling tasks, and also returns a 'caption' for the
		graphic. 
		"""
		#self.canvas.refresh(force_full_refresh=True)
		#Name file with unix epoch and userid
		relfn = os.path.join(self.parent.imgreldir,'amwo_%s_%d.png' % (str(self.userid),
			int(time.mktime(datetime.datetime.now().timetuple()))))
		absfn = os.path.join(self.parent.rootdir,relfn)
		if self.controlstate['gif_mode']:
			self.gif_frames.append(absfn)
		self.canvas.text(.01,.94,self.controlstate['descstr'],
			fontsize=8,verticalalignment='top',color='blue',
			bbox=dict(facecolor='white', edgecolor='blue', boxstyle='round',alpha=.8))
		self.canvas.fig.savefig(absfn,dpi=200)
		#self.canvas.fig.clf()
		#self.canvas.ax = self.canvas.fig.add_subplot(111)
		#Generate caption
		cap = self.syncher.caption
		self.controlstate['thiscaption']=cap
		self.controlstate['thisplot']=relfn
		#Deal with the plot and caption history
		while len(self.plots) > self.n_max_plots:	
			tobedeleted = self.plots.pop(0)
			os.remove(os.path.join(self.parent.rootdir,tobedeleted))
			self.log.info("REMOVED old plot %s" % (tobedeleted))
		self.log.info('Replotted to %s' % (absfn))

		#Store the controlstate that was used to make the plot
		self.controlstate() # store the last controlstate as states[-1]
		self.n_total_plots += 1
		return relfn, cap

	def make_gif(self,gif='out.gif',delay=20,delete_imgs=False):
		"""
		Converts a list of pngs, in order, to frames for a gif
			imgs - list of valid png or jpg paths
			gif - gif file to write to
			tempdir - directory where temporary frame pngs will be stored
			delay - time in milliseconds each frame will display for
		"""
		imgs = self.gif_frames
		tempdir = os.path.join(self.parent.rootdir,self.parent.imgreldir)
		#if not is_ImageMagick_Installed():
		#	raise RuntimeError("ImageMagick appears to not be installed! If on Ubuntu, try sudo apt-get install imagemagick\n")
		self.log.debug("Now beginning to copy files to temporary frames for gif. Temporary directory is %s...\n" % (tempdir))
		paddingcode = '%.'+str(len(str(len(imgs))))+'d' #imagemagick needs zero padded frame numbering
		
		imgext = os.path.splitext(imgs[0])[-1]
		tmpimgs = []
		for i,img in enumerate(imgs):
			tmpimg = os.path.join(tempdir,"img2gif_frame_"+paddingcode % (i+1)+imgext)
			shutil.copy(img,tmpimg)
			tmpimgs.append(tmpimg)

		imcall = "convert -delay %d -loop 0 %s %s" % (delay,os.path.join(tempdir,'img2gif_frame_*'+imgext),os.path.join(tempdir,gif))
		self.log.debug("Calling ImageMagick to convert frames to gif...")
		self.log.debug("Call is %s\n" % (imcall))
		subprocess.check_call(imcall,shell=True)

		self.log.debug("Cleaning up temp files...")
		for tmpimg in tmpimgs:
			os.remove(tmpimg)

		self.gif_frames = []
		return os.path.join(self.parent.imgreldir,gif)
		#if open_gif:
		#	subprocess.check_call("xdg-open %s" % (gif))

	def restart(self):
		"""
		A full 'hard' restart of the backend. Destroys and recreates all of 
		the instances of the AtModWeb components (FakeCanvas, UiHandler, Synchronizer) 
		for this single user. Called if UiHandler receives {posttype:'restart'} as a POST request
		"""
		#A full scale panic restart
		#Just reinitalize all the things
		self.log.warn("---RESTARTING THE BACKEND---")
		#cherrypy.lib.sessions.expire()
		self.uihandler = UiHandler(self)
		self.controlstate = self.uihandler.controlstate
		self.canvas = FakeCanvas(self)
		self.syncher = Synchronizer(self.canvas,self.uihandler)
		self.syncher.refresh(force_full_refresh=True)
		self.replot()
		


class UiDispatcher(object):
	"""
	Makes sure that requests from a particular user's session 
	get dispatched to the proper instances of UiHandler and AtModWebObj
	that contains their plot history. Helps make AtModWeb multiuser.
	a.k.a dispatches requests to the approriate uihandler as 
	specified by the userid cookie.
	"""
	exposed = True

	def __init__(self,muamwo):
		#This needs to be done here (before the UiDispatcher is created) so that CherryPy
		#knows that tools.auth is a thing before it's used in UiDispatcher 
		
		self.muamwo = muamwo

	def get_uihandler(self):
		return self.muamwo.get_user_amwo().uihandler

	def get_amwo(self):
		return self.muamwo.get_user_amwo()

	@cherrypy.tools.accept(media='text/plain')
	@cherrypy.tools.json_out()
	def GET(self, statevar, subfield=None):
		if statevar == 'username':
			uid = self.muamwo.get_userid()
			if uid is not None:
				return {'username':self.muamwo._usernames[uid]}
			else:
				return {'username':''}
		else:
			return self.get_uihandler().GET(statevar=statevar,subfield=subfield)
		
	@cherrypy.tools.json_out()
	@cherrypy.tools.accept(media='text/plain')
	def PUT(self,statevar=None,newval=None,subfield=None):
		return self.get_uihandler().PUT(statevar=statevar,newval=newval,subfield=subfield)

	@cherrypy.tools.accept(media='text/plain')
	@cherrypy.tools.json_out()
	def POST(self, posttype=None):
		if 'authenticate_' in posttype:
			un = posttype.split('authenticate_')[-1] # Anything after is username
			userid = self.muamwo.newuserid()
			self.muamwo._usernames[userid] = un
			respcookie = cherrypy.response.cookie
			respcookie['userid'] = userid
			respcookie['userid']['max-age']=3630
			return {posttype:'true'}
		elif 'kill_' in posttype:
			uid = posttype.split('kill_')[-1]
			uid = str(uid)
			if uid in self.muamwo._usernames:
				self.muamwo.kill(userids=[uid])
			else:
				self.log.error("Recieved kill POST for nonexistant userid %d" % (uid))
		elif 'logout' == 'posttype':
			self.muamwo.logout()
			return {'logout':'true'}
		else: #Push on to appropriate handler
			return self.get_uihandler().POST(posttype=posttype)
	

class MultiUserAtModWebObj(object):
	""" Thin class to spin up AtModWebObj instances when a request comes in from a new user"""
	def __init__(self):
		self.log = logging.getLogger(self.__class__.__name__)
		self._amwo = dict() # AtModWeb instances
		self._usernames = dict()
		#Application Location
		self.uihandler = UiDispatcher(self)
		self.rootdir = os.environ['ATMODWEB_ROOT_DIR'] 
		self.imgreldir = 'www'
		self.docreldir = 'docs'

	@cherrypy.expose
	def restart(self):
		self.get_user_amwo().restart()
		return """<html>Restarting done. </html>"""

	@cherrypy.expose
	def currentplot(self):
		"""
		A link to the currentplot with the proper response headers to trigger a download
		"""
		url = self.get_user_amwo().controlstate['thisplot']
		return cherrypy.lib.static.serve_download(os.path.join(self.rootdir,url))

	@cherrypy.expose
	def console(self):
		uid = self.get_userid()
		#Organize the parameters for each AtModWeb as a table row
		th = OrderedDict()
		th['created'] = 'Time Created'
		th['accessed'] = 'Last Accessed'
		th['username'] = 'Username'
		th['userid'] = 'User ID Number'
		th['nplots'] = 'Number of Plots Created'
		th['kill'] = 'Kill Session'
		tr = copy.deepcopy(th) #OrderedDict for table rows
		retstr = "<html><body>"
		#Handle the kill buttons
		retstr += """
		<link href="www/atmodweb.css" rel="stylesheet" type="text/css">
		<script src="http://ajax.googleapis.com/ajax/libs/jquery/1/jquery.min.js"></script>
		<script> 
		$(document).ready(function(){
			$('.killer').on("click", function (e) {
				var id = $(e.target).attr('name');
				console.log('Killing '+String(id))
				var doingthething = $.ajax({url: "/uihandler",data: {"posttype":"kill_"+String(id)},type: "POST",dataType:"json",
					success : function (json) {
						$(e.target).text('KILLED')
						console.log('Kill success')
					}
				})
			});
		});
		</script>
		"""
		retstr += '<div ID="locationpanel" class="panel">'
		retstr += '<h1>Admin Interface for AtModWeb</h1>'
		retstr += '<p>If you are not the administrator of this application, you should not be here.</p>'
		if uid is not None and self._usernames[uid].lower() == 'liam':
			retstr += "<h1> Currently running amwo instances: </h1>" 
			retstr += "<table>"
			#Add headers to the table
			retstr += "<tr>"
			for field in th:
				retstr += "<th>%s</th>" % (str(th[field]))	
			retstr += "</tr>\n"
			for key in self._amwo:
				tr['username'] = str(self._usernames[key]) if key in self._usernames else 'NO-USERNAME'
				tr['created'] = self._amwo[key].time_created.strftime('%c')
				tr['accessed'] = self._amwo[key].last_accessed.strftime("%c")
				tr['userid'] = '<strong>%s</strong>' % str(key) # Make the username stand out
				tr['nplots'] = str(self._amwo[key].n_total_plots)
				tr['kill'] = """<button ID='kill_%s' class='killer' name='%s' title="Kill this user's session">KILL</button>""" % (key,
					key)
				#Add a row to the table
				retstr += "<tr>"
				for field in th:
					retstr += "<td class='%s'>%s</td>" % (str(key),str(tr[field]))	
				retstr += "</tr>\n"
			retstr += '</table>' 
			retstr += '</div>'
		retstr += "</body></html>"
		return retstr

	@cherrypy.expose
	def data(self):
		cherrypy.response.headers['Content-Type']= 'text/csv'
		uid = self.get_userid()
		data,header = self.get_user_amwo().syncher.data_as_csv()
		return header+'\n'+data

	def kill(self,userids=None):
		"""Kill all specified instance or if userids is not kills any instances that haven't been touched in an hour"""
		if userids is None:
			userids = self._amwo.keys()
			for userid in userids:
				if (datetime.datetime.now() - self._amwo[userid].last_accessed).total_seconds() >= 3600:
					self.log.warn('Session is too old and will be killed for %s: uid %d' % (self._usernames[userid],userid))
					del(self._amwo[userid]) 
					del(self._usernames[userid])
					gc.collect()
		else:
			for userid in userids:
				self.log.warn('Forced to end session for %s: uid %s' % (self._usernames[userid],str(userid)))
				del(self._amwo[userid])
				del(self._usernames[userid])
				gc.collect()

	#Authorization tool
	#This is called whenever a request comes in via a CherryPy Tool
	def check_auth(self,*args, **kwargs):
		"""A tool that looks for a userid cookie, and makes sure that the cookie has an entry in the _usernames"""
		reqcookie = cherrypy.request.cookie
		if 'userid' not in reqcookie:
			#No userid set
			userid = self.newuserid() #Create a new userid and assign it to the user
			self._usernames[userid] = '--pending--'
			respcookie = cherrypy.response.cookie
			respcookie['userid'] = userid
			respcookie['userid']['max-age']=3630
			raise cherrypy.HTTPRedirect("/login")
		else:
			#No username registered to userid
			userid = reqcookie['userid'].value
			if userid not in self._usernames:
				self._usernames[userid] = '--pending--'
				raise cherrypy.HTTPRedirect("/login")

	def logout(self):
		uid = self.muamwo.get_userid()
		del(self._usernames[uid])
		del(self._amwo[uid])
		respcookie = cherrypy.response.cookie
		respcookie['userid']['max-age']=0
		respcookie['userid']['expires']=time.strftime("%a, %d-%b-%Y %T GMT", time.gmtime(time.time()))
		gc.collect()

	def newuserid(self):
		return str(random.randint(0,2**31))

	def get_userid(self):
		reqcookie = cherrypy.request.cookie
		
		#Safety checks
		if 'userid' not in reqcookie:
			return None
		
		userid = reqcookie['userid'].value
		if userid not in self._usernames or self._usernames[userid]=='--pending--':
			return None

		#self.log.info("Request sent to AMWO with userid cookie %s, method %s" % (str(userid),str(cherrypy.request.method)))

		if userid not in self._amwo:
			self._amwo[userid] = AtModWebObj(parent=self,userid=userid)
			self.log.info("Spun up new AMWO instance with userid %s, there are now %d instances running" % (str(userid),len(self._amwo.keys())))
		
		#self.log.debug("Username for id %s is %s" % (str(userid),str(self._usernames[userid])))
		return userid

	def get_user_amwo(self):
		userid = self.get_userid()
		if userid is not None:
			#Update the last accessed time
			self._amwo[userid].last_accessed = datetime.datetime.now()
			return self._amwo[userid]
		else:
			raise cherrypy.HTTPRedirect('/login')


if __name__ == '__main__':
		

	webapp = MultiUserAtModWebObj()
	cherrypy.tools.auth = cherrypy.Tool('before_handler',webapp.check_auth)
	conf = {
		 '/': {
			'tools.sessions.on': True,
			#'tools.sessions.storage_type':"memcached",
			'tools.sessions.locking':'implicit',
			'tools.auth.on': True
		 },
		 '/index': {
			'tools.staticfile.on':True,
			'tools.staticfile.filename': os.path.join(os.path.abspath(webapp.rootdir),'www','atmodweb.html')
		 },
		 '/login': {
			'tools.staticfile.on':True,
			'tools.staticfile.filename': os.path.join(os.path.abspath(webapp.rootdir),'www','login.html')
		 },
		 '/uihandler': {
			 'request.dispatch': cherrypy.dispatch.MethodDispatcher(),
			 'tools.response_headers.on': True,
			 'tools.response_headers.headers': [('Content-Type', 'application/json')],

		 },
		 '/www': {
			 'tools.staticdir.on': True,
			 'tools.staticdir.dir': os.path.join(os.path.abspath(webapp.rootdir),'www'),
			 'tools.expires.on'    : True,
  			 'tools.expires.secs'  : 3600
		 },
		 '/docs': {
			 'tools.staticdir.on': True,
			 'tools.staticdir.dir': os.path.join(os.path.abspath(webapp.rootdir),'doc','build','html'),
			 'tools.expires.on'    : True,
  			 'tools.expires.secs'  : 3600
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
	cherrypy.config.update({'log.screen':False})
	
	cherrypy.log.screen = False
	cherrypy.log.access_log.propagate = False

	cherrypy.tree.mount(webapp, '/',conf)
	cherrypy.engine.start()
	cherrypy.engine.block()
