        /*
            The whole ajax example
            $.ajax({
            // The URL for the request
            url: "post.php",
            
            // The data to send (will be converted to a query string)
            data: {
            id: 123
            },
            
            // Whether this is a POST or GET request
            type: "GET",
            
            // The type of data we expect back
            dataType : "json",
            
            // Code to run if the request succeeds;
            // the response is passed to the function
            success: function( json ) {
            $( "<h1>" ).text( json.title ).appendTo( "body" );
            $( "<div class=\"content\">").html( json.html ).appendTo( "body" );
            },
            
            // Code to run if the request fails; the raw request and
            // status codes are passed to the function
            error: function( xhr, status, errorThrown ) {
            alert( "Sorry, there was a problem!" );
            console.log( "Error: " + errorThrown );
            console.log( "Status: " + status );
            console.dir( xhr );
            },
            
            // Code to run regardless of success or failure
            complete: function( xhr, status ) {
            alert( "The request is complete!" );
            }
            
            });
        */
        var debug = true;

        $(document).ready(function(){
            $plottype_sel = $("#plottype_select");
            
            //Select elements that choose variables
            $xvar_sel = $("#xvar_select");
            $yvar_sel = $("#yvar_select");
            $zvar_sel = $("#zvar_select");
            
            //Make an object that associates selectors backwards with their name and associated bounds and log objects
            $selobj = {};
            $selobj[$xvar_sel.attr("name")] = {'sel':$("#xvar_select"),'boundsmin':$("#xboundsmin"),'boundsmax':$("#xboundsmax"),'log':$("#xlog")};
            $selobj[$yvar_sel.attr("name")] = {'sel':$("#yvar_select"),'boundsmin':$("#yboundsmin"),'boundsmax':$("#yboundsmax"),'log':$("#ylog")};
            $selobj[$zvar_sel.attr("name")] = {'sel':$("#zvar_select"),'boundsmin':$("#zboundsmin"),'boundsmax':$("#zboundsmax"),'log':$("#zlog")};
            
            //Selectors for related controls
            $all_var_sel = $("#xvar_select, #yvar_select, #zvar_select")
            $all_var_log = $("#xlog,#ylog,#zlog")
            $all_var_bounds = $("#xboundsmin,#xboundsmax,#yboundsmin,#yboundsmax,#zboundsmin,#zboundsmax")
            
            //Selector for everything
            $all_controls = $("#model_select, #plottype_select, #xvar_select, #yvar_select, #zvar_select, #xlog, #ylog, #zlog, .xbounds, .ybounds, .zbounds,.dateinput,.positioninput,.dynamicinput")

            //Set up the functions to change controlstates

            //First we must set up the handler for changes on the plottype select

            //Init stuff - set debug options - temporary stuff
            $("#debugpanel").addClass("debug_on").addClass("initialize_me")
            $("#dynamicdriverdiv").addClass("initialize_me")
            $(".debug").hide() // hide debug stuff till we press F1

            //Create progressbar for loding 
            $("#loading_progress").progressbar()
            $("#plot_progress").progressbar()
            $("#plot_progress").hide()

            //-------------------------------------------------------
            //Utility Functions
            //-------------------------------------------------------

            $hide_controls = function(loadstr,defrd) {
                $("#loading_message").text(loadstr)
                $("#loading").hide()
                $("#wrap").hide()
                $("#loading_progress").progressbar("enable")
                defrd.progress(function(msg,newval) {
                    var val = $("#loading_progress").progressbar("value")
                    $logit(1,"progressbar","Progress called from deferred, message is "+String(msg)+" newvalue is"+String(newval))
                    $("#loading_progress").progressbar("value",newval)
                    $("#loading_progress_label").text(msg)
                })
                $("#loading").fadeIn(500)
            }

            $show_controls = function () {
                $("#loading_progress").progressbar("value",100)
                $("#loading_progress_label").text("Done!")
                $("#loading_progress").progressbar("disable")
                $("#wrap").fadeIn(500)
                $("#loading").fadeOut(500)
            }

            

            //Make a debugging console log printing thing to put in ajax error
            $generic_error_func = function (jqxhr,status,error) {
                if (debug) {console.log("Ajax failed: Server says: "+jqxhr.responseText)};
            }

            $generic_put_err = function (jqxhr,status,error) {
                if (debug == true) {
                    alert("Failed to PUT value")
                }
            }

            $generic_put_err = function (jqxhr,status,error) {
                if (debug == true) {
                    alert("Failed to GET value")
                }
            }

            $generic_ajax_alert = function (jqxhr,status,error) { 
                if (debug == true) {
                    alert("AJAX ERR: "+jqxhr.responseText);
                } 
            }

            //Need the myself to call recursively
            //$num2str = function myself  (nums) {
            //    var str = ''
            //    if ($.isArray(nums)) {
            //        //If this is an array we will have to format it approriately
            //
            //    } else {
            //
            //    }
            //}
            $format_number = function myself (num) {
                try {
                    if ( $.isArray(num) ) {
                        for (var i = 0; i < num.length; i++) {
                            num[i] = myself(num[i])
                        }
                    } else {
                        if (Math.abs(num) > 10000 || (Math.abs(num) < .00001 && num !== 0)) {
                            num = num.toExponential(2)
                        } else {
                            num = num.toFixed(2) // 2 decimal places
                        }
                    }
                    return num
                } catch (e){
                    $logit(2,'Formating Number',e.name+" has be caught. Message ="+e.message)
                    return String(num)
                }
            }

            //Deal with padding zero values so things look sensible because...javascript
            $pad = function (str, max) {
                 str = str.toString();
                return str.length < max ? $pad("0" + str, max) : str;
            }

            //Nice litte convenience function for turning an array of promises/deferreds into one via $.when
            $.whenall = function(arr) { return $.when.apply($, arr); };

            //Custom Logging Function, Python Style
            $loglevel= 5; 
            $logarr = ['ATMODWEB LOG'];
            $logon = false;
            $logit = function(level,context,message) {
                var now = Date.now()
                var logstr = "["+String(now)+"]"+"["+context+"] "
                var levels = ["ERROR","WARNING","INFO","DEBUG","PEDANTIC"]
                logstr = logstr+String(levels[level-1])+": "+message
                if ($logon && $loglevel >= level) { $logarr.push(logstr) }
                if(debug && $loglevel >= level) { console.log(logstr) }
            }
            
            $cblog = function(level,evnt,message) {
                //Output a sensible callback for the event
                var callername = $(evnt.target).attr("name")
                var callerid = $(evnt.target).attr("ID")
                //console.log(String(callername),String(callerid))
                if (callername == null) {
                    $logit(level,"CALLBACK: "+callerid+':'+String(evnt.type), message)
                } else {
                    $logit(level,"CALLBACK: "+callername+':'+String(evnt.type), message)
                }
            }

            //Checks if any of the selects have Latitude,Longitude or Altitude,
            //and hides the associated control if they do (since it's then an independant variable)
            $hidePosIfNeeded = function () {

                var def = $.Deferred()
                $logit(3,"$hidePosIfNeeded","Now hiding position if needed.")
                var xvar = $xvar_sel.val()
                var yvar = $yvar_sel.val()
                var zvar = $zvar_sel.val()
                if ( $.isArray(xvar) ){ xvar = xvar[0] };
                if ( $.isArray(yvar) ){ yvar = yvar[0] };
                if ( $.isArray(zvar) ){ zvar = zvar[0] };
                
                var lat_in = $.inArray("Latitude",[xvar,yvar,zvar]) != -1
                var lon_in = $.inArray("Longitude",[xvar,yvar,zvar])  != -1
                var alt_in = $.inArray("Altitude",[xvar,yvar,zvar]) != -1
                if (debug == true) { console.log([xvar,yvar,zvar])}
                if (debug == true) { console.log([lat_in,lon_in,alt_in])}
                //$("#latinputlbl").hide()
                //$("#loninputlbl").hide()

                //if (lat_in) { $("#latinput").attr('disabled',true) } else { $("#latinput").removeAttr('disabled') } 
                //if (lon_in) { $("#loninput").attr('disabled',true) } else { $("#loninput").removeAttr('disabled') }
                //if (alt_in) { $("#altinput").attr('disabled',true) } else { $("#altinput").removeAttr('disabled') }
                if (lat_in) { $("#latinputlbl,#latinputbr").hide() } else { $("#latinputlbl,#latinputbr").show() } 
                if (lon_in) { $("#loninputlbl,#loninputbr").hide() } else { $("#loninputlbl,#loninputbr").show() }
                if (alt_in) { $("#altinputlbl").hide() } else { $("#altinputlbl").show() }
    
                        
                def.resolve()
                return def.promise()
            } 

            $.when_all_trigger = function(the_selector,the_event) {
                the_promises = []
                the_names = []
                $(the_selector).each(function (){
                    var the_promise = $(this).triggerHandler(the_event)
                    the_promises.push(the_promise)
                    if (debug == true) { the_names.push($(this).attr("name"))}
                })
                if (debug == true) {console.log("Waiting for "+the_names+" to trigger "+the_event)}
                return $.whenall(the_promises)
            }

            //set all var selects to their value in the controlstate
            $init_sel = function (which_sel) {
                //When we're sure we're initialized, set the option to the currently selected variable in the controlstate
                    var allset = $.Deferred()
                    var waiting_for = []

                    var xname = $xvar_sel.attr("name")
                    var yname = $yvar_sel.attr("name")
                    var zname = $zvar_sel.attr("name")
                    
                    //if (which_sel != xname && which_sel != yname && which_sel != zname && which_sel != 'all') {
                    //    throw "Invalid select to initialize"
                    //}

                    if (debug) { console.log("Initializing the variable selects: "+which_sel)}

                    if (which_sel == xname || which_sel == 'all') {
                        if (debug) { console.log("Initializing the X variable select")}
                    
                        var xvar_sel_set = $.ajax({url: "uihandler",data: {"statevar":xname},type: "GET", 
                            success: function (json) {
                                $xvar_sel.val(json[xname])
                                if (debug == true) { console.log("Init x select to "+json[xname]) }
                            },
                            error: $generic_ajax_alert  
                        })
                        waiting_for.push(xvar_sel_set)
                    }

                    if (which_sel == yname || which_sel == 'all') {
                        if (debug) { console.log("Initializing the Y variable select")}

                        var yvar_sel_set = $.ajax({url: "uihandler",data: {"statevar":yname},type: "GET", 
                            success: function (json) {
                                $yvar_sel.val(json[yname])
                                if (debug == true) { console.log("Init y select to "+json[yname]) }
                            },
                            error: $generic_ajax_alert
                        })
                        waiting_for.push(yvar_sel_set)
                    }

                    if (which_sel == zname || which_sel == 'all') {
                        if (debug) { console.log("Initializing the Z variable select")}
                    
                        var zvar_sel_set = $.ajax({url: "uihandler",data: {"statevar":zname},type: "GET", 
                            success: function (json) {
                                $zvar_sel.val(json[zname])
                                if (debug == true) { console.log("Init z select to "+json[zname]) }
                            },
                            error: $generic_ajax_alert
                        })
                        waiting_for.push(zvar_sel_set)
                    }

                    $.whenall(waiting_for).done(allset.resolve) //Apparently .done is the right choice
                    //it apparently filters out non-functions and deals properly with multiple inputs
                    return allset.promise()
            }

            $format_caption = function (csstring) {
                //Turns a comma-seperated string into a ul
                if (debug == true) { console.log("Formatting caption") }
                var values = csstring.split('|') //split on pipes incase there are any commas in data
                var theul = '<ul ID="captionlist" class="captionlist">' 
                for (v in values) {
                    theul=theul+'<li class="captionlist">' + values[v] + '</li>'
                }
                theul=theul+'</ul>'
                //if (debug == true) { console.log("Done") }
                return theul
            }

            starting_up = $.Deferred()
            $hide_controls("Prepare for launch!",starting_up)

            //-----------------------------------------------------
            //Handlers which initialize or update UI control values
            //-----------------------------------------------------

            //$("#username").on("focus",function(e) {
            //    e.preventDefault();
            //    $cblog(5,e,"In callback")
            //    var myname = $(e.target).attr("name")
            //    //Use the name attr of the input to decide what field of the datetime object we will get
            //    
            //    var doneprocessing = $.ajax({url: "/uihandler",data: {"statevar":myname},type: "GET",dataType:"json",
            //        success: function(json) {
            //            var newval = json[myname]
            //            $cblog(3,e,"Username from backend is: "+json[myname])
            //            $(e.target).val(json[myname])
            //        }
            //    })
            //    return doneprocessing
            //})

            

            $plottype_sel.on("focus",function(e) {
                e.preventDefault();
                $cblog(5,e,"In callback")
                var myname = $(e.target).attr("name")
                var done = $.Deferred()
                //Use the name attr of the input to decide what field of the datetime object we will get
                
                var doneprocessing = $.ajax({url: "/uihandler",data: {"statevar":myname},type: "GET",dataType:"json",
                    success: function(json) {
                        var newval = json[myname]
                        $cblog(3,e,"Plottype from backend is: "+json[myname])
            			if (newval != $(e.target).val()) {
            				$(e.target).val(json[myname])
                            $cblog(3,e,"Plottype changed to: "+newval)
            				var changedtype = $plottype_sel.triggerHandler("change")
            				$.when(changedtype).then(done.resolve())
            				$(e.target).fadeOut(200).fadeIn(200)
            			}
                    }
                })
                return $.when(doneprocessing).then(done)
                //e.preventDefault()
            });


            //--X,Y and Z Variable Selects 
            $all_var_sel.on("focus",function( e ) {
                e.preventDefault();
                $cblog(5,e,"In callback")
                //Initialize it if it asks for it
                var myname = $(e.target).attr("name")
                //get what is selected so we can decide if it's sane given the new options
                var selection = $(e.target).val()
                var initializing = $.Deferred()
                $cblog(4,e,"selection before initialize is "+selection)
                if ( $(e.target).hasClass("initialize_me") ){
                    $cblog(4,e,"has initialize_me class, AJAXing in options.")
                    //Get the list of valid options we can use from the backend (from the session)
                    var spawning_options = $.ajax({url: "/uihandler",data: {"statevar":myname+"_options"},type: "GET",
                        success: function( json ) {
                            //Populate the list
                            $("option",e.target).remove(); //All options under this
                            //if (debug == true) { console.log(json) }
                            $.each(json[myname+"_options"], function(key, value) {
                                //Set the option value to the key, and the html to the value
                                $(e.target).append($('<option>', { value : key }).text(value))
                                $cblog(5,String(myname)+": success","Added option "+String(key)+" , "+String(value))
                            });
                                                    
                        }
                    });
                    //Remove the initilization tag from the select
                    $(e.target).removeClass("initialize_me")
                    //Set the initializing deferred to resolved once we've 

                    //Make sure the current selection is a valid option, otherwise change it and trigger "change"
                    $.when(spawning_options).then(function () {
                        var checkingSelection = $.Deferred()
                        var optionValues = [];
                        $('option',e.target).each(function() {
                            optionValues.push($(this).val());
                        });
                        if ( !$.inArray(selection,optionValues) ) {
                            $cblog(2,e,"Option "+selection+" is not sane, defaulting to "+optionValues[0])
                            $(e.target).val(optionValues[0])
                            $.when($(e.target).triggerHandler("change")).then(checkingSelection.resolve)
                        } else {
                            checkingSelection.resolve()
                        }
                        return checkingSelection.promise()
                    }).then($init_sel(myname))
                    .then($selobj[myname]['boundsmin'].triggerHandler("focus"))
                    .then($selobj[myname]['boundsmax'].triggerHandler("focus"))
                    .done(initializing.resolve)
                } else {
                    $.when($selobj[myname]['boundsmin'].triggerHandler("focus"),$selobj[myname]['boundsmax'].triggerHandler("focus"))
                    .done(initializing.resolve)
                }
                
                return initializing.promise()
                //e.preventDefault()
            });

            //--X, Y, and Z Limit Inputs
            $all_var_bounds.on("focus",function(e) {
                e.preventDefault();
                $cblog(5,e,"In callback")
                var myname = $(e.target).attr("name")
                var the_ajax = $.ajax({url: "/uihandler",data: {"statevar":myname},type: "GET",
                    success: function(json){
                        var newbounds = json[myname]
                        if ($.isArray(newbounds[0])) {
                            //We don't want multiple limits
                            newbounds = newbounds[newbounds.length-1]
                        }
                        //console.log(newbounds)
                        if ( $(e.target).hasClass('max') ) {
                            var newval = $format_number(newbounds[1]) //Use the second number in the comma separated string
                        } else if ( $(e.target).hasClass('min') ){
                            var newval = $format_number(newbounds[0]) //Use the first number in the comma separated string
                        }
                        if ($(e.target).val() != newval) {
                            $(e.target).val(newval)
                            $(e.target).fadeOut(200).fadeIn(200) 
                            $cblog(4,e,"Bounds changed to "+newval)
                        }
                        
                    }
                });
                return the_ajax
                //e.preventDefault()
            });

            //--Date Entry Inputs
            $(".dateinput").on("focus",function(e) {
                e.preventDefault();
                $cblog(5,e,"In callback")
                var myname = $(e.target).attr("name")
                //Use the name attr of the input to decide what field of the datetime object we will get
                
                var dtpadding = {"year":4,"month":2,"day":2,"hour":2,"minute":2}

                var the_ajax = $.ajax({url: "/uihandler",data: {"statevar":"datetime","subfield":myname},type: "GET",dataType:"json",
                    success: function(json) {
                        newval = $pad(json["datetime"],dtpadding[myname])
                        if ( newval != $(e.target).val() ) {
                            $(e.target).val(newval)
                            $(e.target).fadeOut(200).fadeIn(200)
                            $cblog(4,e,"value changed to "+json["datetime"])
                        }
                        
                    }
                })
                return the_ajax
                //e.preventDefault()
            });

            //--Latitude, Longitude, Altitude Input Elements
            $(".positioninput").on("focus",function(e) {
                e.preventDefault();
                $cblog(5,e,"In callback")
                var myname = $(e.target).attr("name")
                //Use the name attr of the input to decide what field of the datetime object we will get
                
                var the_ajax = $.ajax({url: "/uihandler",data: {"statevar":myname},type: "GET",dataType:"json",
                    success: function(json) {
                        var newval = String(json[myname])
                        if ($(e.target).val() != newval){
                            $(e.target).val(newval)
                            $(e.target).fadeOut(200).fadeIn(200)
                        }
                        $cblog(4,e,"stringified value from backend is "+newval)
                    }
                })
                return the_ajax
                //e.preventDefault()
            });

            //--Driver Entry Inputs Are Dynamically Created
            //--so must be rebound when they are created
            //--look for them bound to the main document click handler below

            

            //-------------------------------------------------------------------
            //Handlers which put new values to backend controlstate (on "change")
            //-------------------------------------------------------------------

            //--The Type of Plot Chooser Select
            $plottype_sel.on("change",function(e) {
                $cblog(5,e,"In callback")
                var selection = $(e.target).val();
                var defrd = $.Deferred() //This is so we can check if the callback finished
                //Tell the backend that we have a change to the plotvar
                //{"statevar":"plottype","newval":selection}
                $cblog(4,e,"selection is "+String(selection)) 

                var plottype_changed = $.ajax({url: "/uihandler",data: {"statevar":"plottype","newval":selection},type: "PUT"})

                if (selection == "line") {
                    //If we are plotting a line, then don"t bother showing the color variable select
                    
                    //Trigger the xvar, yvar to populate
                    
                    $(".xvar").show()  
                    $xvar_sel.addClass("initialize_me")
                    $xvar_sel.attr("multiple","true")
                    $("#xlog_label").show()
                    
                    $(".yvar").show()  
                    $yvar_sel.addClass("initialize_me")
                    $yvar_sel.attr("multiple","true")
                    $("#ylog_label").show()
                    
                    $(".zvar").hide();
                    $zvar_sel.removeAttr("multiple")
                }

                if (selection == "pcolor")
                {
                    $(".zvar").show()
                    
                    $(".xvar").show()                    
                    $xvar_sel.addClass("initialize_me")
                    $xvar_sel.removeAttr("multiple")
                    $("#xlog_label").hide()

                    $(".yvar").show()
                    $yvar_sel.addClass("initialize_me")
                    $yvar_sel.removeAttr("multiple")
                    $("#ylog_label").hide()

                    $zvar_sel.addClass("initialize_me")
                    $zvar_sel.removeAttr("multiple")
                    $("#zlog_label").show()

                }

                if (selection == "map")
                {   
                    //var xvar_trigger = $xvar_sel.val("Longitude").triggerHandler("change")
                    //var yvar_trigger = $yvar_sel.val("Latitude").triggerHandler("change")
                    //Update the Deferred so that yvar and xvar selects are ensured to be the correct values (Longitude and Latitude)
                    //after everything is done

                    //defrd.done(xvar_trigger,yvar_trigger)

                    $(".zvar").show()
                    
                    $xvar_sel.addClass("initialize_me")
                    $xvar_sel.removeAttr("multiple")
                    $("#xlog_label").hide()
                    $(".xvar").hide()
                    
                    $yvar_sel.addClass("initialize_me")
                    $yvar_sel.removeAttr("multiple")
                    $("#ylog_label").hide()
                    $(".yvar").hide()
                    
                    $zvar_sel.addClass("initialize_me")
                    $zvar_sel.removeAttr("multiple")
                    $("#zlog_label").show()
                        
                }
                
                $all_var_log.prop("checked",false)
                
                $.when(plottype_changed).done(function (data) {
                    
                    $cblog(4,e,"triggering focus from plottype change") 
                    return $.when_all_trigger($all_var_log,'change').then($.when_all_trigger($all_var_sel,"focus")).then(defrd.resolve);
                })
            
                return defrd.promise() //Return a Deferred so we can see if the callback finished
            });

            //--Model Select Dropdown
            $("#model_select").on("change",function(e) {
                var changing_model = $.Deferred()
                $hide_controls("Changing models to: "+ $(e.target).val(),changing_model)
                changing_model.notify("Running "+$(e.target).val()+"...",5)
                $cblog(5,e,"In callback")
                var myname = $(e.target).attr("name")
                var selection = $(e.target).val()
                $cblog(4,e,"selection is "+String(selection))
                var putting_new_model = $.ajax({url: "/uihandler",data: {"statevar":myname,"newval":selection},type: "PUT",
                            success: function (ret) {
                                changing_model.notify("Updating UI...",75)
                                $("#dynamicdriverdiv").addClass("initialize_me") // Reinit drivers dropdown
                                $all_var_sel.addClass("initialize_me")
                                $cblog(3,e,"dynamic driver div told to reinit,triggering all focus") 
                                return $.when($.when_all_trigger($all_controls,"focus")).then($("#dynamicdriverdiv").triggerHandler("click")).then($init_sel('all')).then($show_controls)
                            }   
                })

                return $putting_new_model
            });

            $("#model_select").on("focus",function(e) {
                
                $cblog(5,e,"In callback")
                var myname = $(e.target).attr("name")
                var oldval = $(e.target).val()
                $cblog(4,e,"selection is "+String(oldval))
                var checking_model = $.ajax({url: "/uihandler",data: {"statevar":myname},type: "GET",
                            success: function (json) {
                                $cblog(5,e,"New model is: "+String(json[myname]))
                                $(e.target).val(json[myname])
                            }
                }) //Chain in the check to see if we need to trigger the change event
                .then(function () {
                    //Call the changed handler if nessecary
                    if ( oldval !== $(e.target).val() ){
                        $cblog(4,e,"Model name has changed, triggering change event")
                        return $(e.target).triggerHandler("change")
                    }
                    else {
                        var def = $.Deferred().resolve() 
                        return def.promise() //Just return a pre-resolved deferred
                    }    
                });

                return checking_model
            });

            //Hide it for now because it doesn't work
            $(".model").hide()
            
            //--X,Y,Z Variable Select Dropdowns 
            $all_var_sel.on("change",function(e) {
                $cblog(5,e,"In callback")
                //We use the name attribute to know what controlstate variable the select sets
                var myname = $(e.target).attr("name")
                var selection = $(e.target).val()
                var statevar = String(myname.charAt(0)+"multi")
                var change_done = $.Deferred()

                //Handles formating the data for PUT ajax calls
                if ( $.isArray(selection) && selection.length > 1) {
                    $cblog(4,e,"Multiple selection is ON, and selection length is "+String(selection.length)+"selection is"+String(selection))
                    var multi_updated = $.ajax({url: "/uihandler",data: {"statevar":statevar,"newval":true},type: "PUT"})
                } else if ( $.isArray(selection) && selection.length == 1 ) {
                    $cblog(4,e,"Multiple selection is ON, but selection length is 1, selection is"+String(selection)) 
                    selection = selection[0]
                    var multi_updated = $.ajax({url: "/uihandler",data: {"statevar":statevar,"newval":false},type: "PUT"})
                    
                } else {
                    $cblog(4,e,"Multiple selection is OFF, selection is"+String(selection)) 
                    var multi_updated = $.ajax({url: "/uihandler",data: {"statevar":statevar,"newval":false},type: "PUT"}) 
                }
                
                
                //Have to do something odd to pass an array to cherrypy with jquery, use 'traditional' param parsing mode
                multi_updated.done( function(data) {
                    $cblog(4,e,"Done updating multi.") 
                    
                    var ajax_done = $.ajax({url: "/uihandler",data: $.param({"statevar":myname,"newval":selection}, true),type: "PUT"})
                    //Make sure the bounds are up to date
                    
                    $.when(ajax_done)
                    .then($selobj[myname]['sel'].triggerHandler("focus"))
                    .then($.when_all_trigger("."+myname[0]+"bounds","focus"))
                    .then($hidePosIfNeeded).then($.when_all_trigger(".positioninput","focus")).done(function(){
                        change_done.resolve()
                        $cblog(4,e,"Done chaining focus after updating multi.") 
                    })
                    
                });

                return change_done.promise()
                
            });

            //--X, Y and Z Log Checkboxes
            $all_var_log.on("change",function(e) {
                $cblog(5,e,"In callback")
                var myname = $(e.target).attr("name")
                var newval = $(e.target).prop("checked")
                $cblog(4,e,"checked property is: "+String(newval))
                $('#xlog,#ylog,#zlog').each(function (ind,logsel) {
                    if ( myname != $(logsel).attr("name")) {
                         if ( newval === true ) {
                            $(logsel).attr('disabled','disabled')
                            $cblog(4,e,"Setting log checkbox "+String($(logsel).attr("name"))+" to disabled")
                        } else {
                            $(logsel).removeAttr('disabled')
                            $cblog(4,e,"Setting log checkbox "+String($(logsel).attr("name"))+" to enabled")
                        }
                    } 
                })
                return $.ajax({url: "/uihandler",data: {"statevar":myname,"newval":newval},type: "PUT"})
                
            });

            //--X, Y, and Z Bounds Inputs
            $all_var_bounds.on("change",function(e) {
                $cblog(5,e,"In callback")
                var myid = $(e.target).attr("ID")
                var myname = $(e.target).attr("name")
                var myval = $(e.target).val()
                //var temp = newval.split(',') //Try to split up by commas
                //figure out if it was the minimum or maximum input
                //that triggered the event
                if ( $(e.target).hasClass('max') ) {
                    var mysibval = $('#'+myid.split('bounds')[0]+"boundsmin").val()
                    newval = [mysibval,myval]
                    $cblog(4,e,"Determined that max limit generated event, sibling value is "+String(mysibval))
                } else if ( $(e.target).hasClass('min') ) {
                    var mysibval = $('#'+myid.split('bounds')[0]+"boundsmax").val()
                    newval = [myval,mysibval]
                    $cblog(4,e,"Determined that min limit generated event, sibling value is "+String(mysibval))
                } else {
                    alert("Error while determining if the maximum or minimum limit was changed. Please report this bug.")
                    return $.Deferred().resolve() //Return nothing but an empty resolved deferred
                }

                //Have to do something odd to pass an array to cherrypy with jquery, use 'traditional' param parsing mode
                putting_bounds = $.ajax({url: "/uihandler",data: $.param({"statevar":myname,"newval":newval},true),type: "PUT",
                    error: function (e) {
                        alert("Unable to complete bounds update. Please make sure your bounds were formatted correctly (always include decimal point)")
                    }
                })
                
                return $.when(putting_bounds).then($('#plotbutton').triggerHandler("click"))
                //return putting_bounds
            
            });

            //--Date Change Inputs
            $(".dateinput").on("change",function(e) {
                $cblog(5,e,"In callback")
                //Use the name attr of the input to decide what field of the datetime object we will set
                var myname = $(e.target).attr("name")
                var newval = $(e.target).val()
                $cblog(4,e,"value is: "+newval)
                //{"statevar":"datetime","newval":{myname : parseInt(newval)}}
                var ajax_done = $.ajax({url: "/uihandler",data: {"statevar":"datetime","subfield":myname,"newval":parseInt(newval)},type: "PUT"})
                var plotting = $.when(ajax_done).then($("#plotbutton").triggerHandler("click"))
                return plotting
                //return ajax_done
            });

            //--Position Change Inputs
            $(".positioninput").on("change",function(e) {
                $cblog(5,e,"In callback")
                //Use the name attr of the input to decide what field of the datetime object we will set
                var myname = $(e.target).attr("name")
                var newval = $(e.target).val()

                $cblog(4,e,"value is: "+newval)

                //{"statevar":"datetime","newval":{myname : parseInt(newval)}}
                var ajax_done = $.ajax({url: "/uihandler",data: {"statevar":myname,"newval":newval},type: "PUT"})
                //var autoscale_done = $.ajax({url: "/uihandler",data: {"posttype":"autoscale"},type: "POST"})
                var plotting = $.when(ajax_done).then($("#plotbutton").triggerHandler("click"))
                return plotting
                //return $.when(ajax_done).then(autoscale_done)
            });

            
            //---Handle clicking the plot button---
            $('#plotbutton').on('click',function(e) {
                e.preventDefault();
                $cblog(5,e,"In callback")
                //Tell the backend to work through any UI changes and replot
                var plotting_done = $.Deferred()

                //Put in the loading sign
                $("#plotimg").attr("src","/www/loading.gif").fadeIn(200)

                var refreshing = $.ajax({url: "/uihandler", data: {"posttype":"refreshnow"},type: "POST",
                    error: function(jqxhr,status,error) {
                        
                        $cblog(1,e,"FAILED on refreshnow POST, error was "+jqxhr.responseText)
                        var getting_error = $.ajax({url: "/uihandler", data: {"statevar":"lasterror"},type: "GET",
                            success: function (json) {
                                alert("Oops, I couldn't refresh your plot. Please check that your selections make sense.\n "+String(json['lasterror']))
                            $("#plotimg").attr("src","/www/error.png").fadeIn(200)
                            }
                        })
                        return getting_error
                        
                    }

                })

                $.when(refreshing).then(function (thedata) {
                    //Tell the backend to save the plot and return the url to the image
                    $cblog(4,e,"refreshnow POST succeeded, now attempting to plot")
                    var done_replotting = $.ajax({url: "/uihandler", data: {"posttype":"replotnow"},type: "POST",dataType: "json",
                        success: function( json ) {
                            $cblog(4,e,"replotnow POST succeeded adding plot "+json["src"])
                            $cblog(5,e,"caption is "+json["cap"])

                            $("#plotimg").attr("src",json["src"]).fadeIn(200);    
                            $("#plotimg_cap").html($format_caption(json["cap"]))
                            $("#dynamicdriverdiv").addClass('initialize_me')
                            $driver_reinit = true
                        },
                        error : function ( jqxhr ) {
                            $cblog(1,e,"FAILED replotnow POST request text is: "+jqxhr.responseText)
                            alert("Oops, I was unable to save your plot. Please change your selections and try again.")
                            $("#plotimg").attr("src","/www/error.png").fadeIn(200)
                        }
                        
                    }) //ajax done
                    //Make sure position and date are up to date
                    return done_replotting
                    })//then done
                    .then(function (f3) {
                        $cblog(4,e,"Now triggering dynamicdriverdiv click handler")
                        return $("#dynamicdriverdiv").triggerHandler("click")
                        })
                    .then($.when_all_trigger($all_controls,"focus"))
                    .then($("#driverchart").triggerHandler('focus')) //Update the driver chart
                    .done(function (f) {
                        $cblog(4,e,"done with plotting, resolving main Deferred.")
                        plotting_done.resolve()
                    })
                
                return plotting_done.promise()
            });
      
            //Handle clicking the rescale graph button
            //---------------------------------------------------
            $('#autoscalebutton').on("click", function (e){
                $cblog(5,e,"In autoscale callback")
                var autoscaling = $.ajax({url: "/uihandler", data: {"posttype":"autoscale"},type: "POST",dataType: "json",
                    success: function (json) {
                        //refresh the controls
                        return $.when_all_trigger($all_controls,"focus")
                        .done($("#plotbutton").triggerHandler("click")) 
                    }
                })
            });

            //Handle clicking the "Download Data" button
            //---------------------------------------------------
            $('#databutton').on("click", function (e){
                $cblog(5,e,"In databutton callback")
                window.open('/data')
            });

            //Handle clicking the "Download Graph" button
            //---------------------------------------------------
            $('#graphbutton').on("click", function (e){
                $cblog(5,e,"In graphbutton callback")
                window.location.assign('/currentplot')
            });


            //This function operates on a dynamic driver chart data
            //object and finds the F10.7 and 81 day F10.7 average, and
            //computes the estimated EUV flux using the formula:
            //
            //  EUV = 1.6 * .032(F_10.7 + F_10.7_81)/2 
            //
            $addEUV = function (ddcd) {
                //Takes dynamic driver data and adds estimated EUV
                var ind107 = ddcd.map(function(x) {return x.name; }).indexOf('f107');
                var ind107a = ddcd.map(function(x) {return x.name; }).indexOf('f107a');
                var indeuv = ddcd.map(function(x) {return x.name; }).indexOf('EUV');
                
                if ( ind107 !== -1 ) {
                    //if both are present
                    var f107 = ddcd[ind107].value
                    var themin = ddcd[ind107].min
                    var themax = ddcd[ind107].max
                    
                    if ( ind107a !== -1 ){
                        var f107a = ddcd[ind107a].value;
                    } else {
                        var f107a = ddcd[ind107].value;
                    }
                    var f102euv = function (f107,f107a) {
                        return 1.6 + .032*(Number(f107)+Number(f107a))/2
                    }
                    var newobj = {name:'EUV',
                                    min:f102euv(themin,themin).toFixed(3),
                                    max:f102euv(themax,themax).toFixed(3),
                                    value:f102euv(f107,f107a).toFixed(3),
                                    units:"10^14 photon/s/m^2",
                                    desc:"Estimated Extreme Ultraviolet Photon Flux"}
                    if ( indeuv === -1 ) {
                        ddcd.push(newobj)
                    } else {
                        ddcd[indeuv] = newobj
                    }
                    $cblog(4,'addEUV','Adding EUV flux '+String(newobj.value)+" equiv to F10.7 "+String(f107))
                }
                return ddcd
            }

            $("#driverchart").on("focus",function (e){

                var thedef = $.Deferred()

                var updating_chart = $.ajax({url: "/uihandler",data: {"statevar":"chartdata"},type:"GET",
                    success: function(json){
                       
                        //Use the driver ranges to update the chart data
                        var data = [] //Initialize an empty object

                        //Build up the data object from the json return from ajax GeT
                        $.each(json['chartdata'], function(driver,dataline){
                            var driverval = Number(dataline['data']) //Value of input converted to number
                            var driverunits = dataline['units'] 
                            var driverdesc = dataline['descriptions'] 
                            var driverrange = dataline['ranges'] 

                            $cblog(5,e,"Driver "+String(driver)+"has value "
                                                +String(driverval)+", range "
                                                +String(driverrange)+", units "
                                                +String(driverunits)+", desc"
                                                +String(driverdesc))

                            if ( !isNaN(driverval) ) {
                                var newobj = {name:driver,value:driverval,
                                              min:Number(driverrange[0]),
                                              max:Number(driverrange[1]),
                                              units:driverunits,
                                              desc:driverdesc};
                                data.push(newobj);
                                
                            }

                        });

                        //Append the EUV flux
                        data = $addEUV(data)

                        //Update the chart
                        $cblog(4,e,"After: "+String(data));
                        
                        var thechart = d3.select(".chart")
                                    .selectAll("div")
                                    .data(data)
                        
                        var color = d3.scale.linear()
                                    .domain([0,.5, 1])
                                    .range(["seagreen","orange", "red"]);
                        
                        thechart.transition()
                                    .style("width", function(d) { return (d.value-d.min)/(d.max-d.min) * 100 + "%"; })
                                    .style("background-color", function(d) { return color((d.value-d.min)/(d.max-d.min))})
                                    .text(function(d) { return d.name+': '+String(d.value); });

                        thechart.enter().append("div")
                                            .style("width", function(d) { return (d.value-d.min)/(d.max-d.min) * 100 + "%"; })
                                            .style("background-color", function(d) { return color((d.value-d.min)/(d.max-d.min))})
                                            .text(function(d) { return d.name+':'+String(d.value); })
                                            .on("mouseover", function(d) {
                                                d3.select(this).style("font-size","14px")
                                                    .text(d.desc+"["+String(d.units)+"]: "+$format_number(d.value)+" range: ("+String(d.min)+"-"+String(d.max)+")");
                                            })
                                            .on("mouseout", function(d) {
                                                d3.select(this).style("font-size","10px")
                                                    .text(d.name+':'+String(d.value));
                                            });
                                            
                        thechart.exit()
                            .remove()        

                    } //end of success function
                }); //end of the ajax

                thedef.resolve()

                return thedef.promise()

            })


            //--Drivers inputs that are Ajaxed in
            $("#dynamicdriverdiv").on("click", function (e) {
                e.preventDefault();
                $cblog(5,e,"In callback")
                var all_done = $.Deferred()
                $cblog(4,e,"Dynamic drivers click callback. Has init class:"+String($("#dynamicdriverdiv").hasClass('initialize_me')));

                if ( $("#dynamicdriverdiv").hasClass('initialize_me') || $driver_reinit == true) {
                    //make sure the controlstate is up to date. Strictly this isn't nessecary
                    //var refreshing = $.ajax({url: "/uihandler", data: {"posttype":"refreshmodeloptions"},type: "POST"})
                    //$(".dynamicinput").remove()

                    //Get all the driver inputs/labels/breaks 
                    theinputs = $(".dynamicinput")
                    
                    var getting_drivers = $.ajax({url: "/uihandler",data: {"statevar":"drivers"},type:"GET",
                        success: function(json){
                            $cblog(4,e,"Now building dynamic drivers list");
                            var bigselector = ''
                            
                            $.each(json["drivers"], function(key,value) {
                                //Check if the input type is date or array
                                //if ( key === 'dt' || $.isArray(value) ){
                                if ( $.isArray(value) ){
                                    return true; //Forces jQuery to skip this loop iteration   
                                }
                                $cblog(5,e,"Adding driver "+key+" : "+value)
                                
                                //Add to selector text that will select everything we're now creating
                                bigselector = bigselector+"#dynamicinput"+key+' '+"#dynamicinputlabel"+key+' '

                                //If we already have a field, don't overwrite it.
                                var theinput = $("#dynamicinput"+key)
                                var thelabel = $("#dynamicinputlabel"+key)
                                var thebreak = $("#dynamicinputbr"+key)

                                //Everything but the input we are currently working on
                                theinputs = theinputs.not(theinput).not(thelabel).not(thebreak)

                                //If the input doesn't yet exist
                                if ( theinput.length==0 ) {
                                    //Dynamically determine the length of the field
                                    var field_size = String(value).length
                                    var valstr = $format_number(value)

                                    //Put a maximum size on the field so we don't get boxes outside the div
                                    if (field_size > 15) { field_size = 15} 

                                    $cblog(4,e,"Creating new input and label for "+String(key)+": "+valstr)
                                    
                                    //Create the input
                                    theinput = $("<input type='text' class='dynamicinput' size="+String(field_size)+">").val(valstr).attr("name",key).attr("ID",'dynamicinput'+key)

                                    //Make a new change callback
                                    theinput.on("change",function(e){
                                        $cblog(5,e,"In callback")
                                        var myname = $(e.target).attr("name")
                                        var textval = $(e.target).val()
                                        $cblog(4,e,"new value is "+textval)
                                        var ajax_done = $.ajax({url: "/uihandler",data: {"statevar":"drivers","subfield":myname,"newval":textval},type: "PUT"})
                                        var plotting_done = $.when(ajax_done).then($("#plotbutton").triggerHandler("click"))
                                        return plotting_done
                                        //return ajax_done
                                    });
                                    
                                    //Make a new focus callback
                                    theinput.on("focus",function(e){
                                        e.preventDefault();
                                        $cblog(5,e,"In callback")
                                        var myname = $(e.target).attr("name")
                                        var textval = $(e.target).val()
                                        $cblog(4,e,"backend value is "+textval)
                                        var ajax_done = $.ajax({url: "/uihandler",data: {"statevar":"drivers","subfield":myname},type: "GET",
                                            success: function (json) {
                                                $cblog(4,e,"value from backend is "+$format_number(json["drivers"]))
                                                $(e.target).val($format_number(json["drivers"]))
                                            }
                                        })
                                        return ajax_done
                                    });
                                    
                                    //Create the label
                                    thelabel = $("<label class='dynamicinput'>").text(key+": ").attr("ID",'dynamicinputlabel'+key)
                                    //Add the label to the main driver div
                                    $("#dynamicdriverdiv").append(thelabel.append(theinput)) 
                                    //Add the input to the label
                                    $("#dynamicdriverdiv").append($("<br class='dynamicinput'>").attr("ID",'dynamicinputbr'+key))

                                } else {
                                    //console.log(theinput.val(),value)
                                    if (theinput.val() != value) {
                                        theinput.val(value)
                                        //Animate the change
                                        theinput.fadeOut(200).fadeIn(200)
                                    }

                                }
                                
                                
                            }) //Loop on all the contents of the returned "drivers" object

                            //Get rid of any straggling inputs that were not in the AJAX'd json   
                            theinputs.remove()

                        } //success function
                    });

                    $("#dynamicdriverdiv").removeClass("initialize_me")
                    $driver_reinit = false

                    var getting_units = $.when(getting_drivers).then($.ajax({url: "/uihandler",data: {"statevar":"drivers_units"},type:"GET",
                        success: function(json){
                            //Put the driver units on the labels
                            $.each(json['drivers_units'],function(key,val){
                                var oldval = $("#dynamicinputlabel"+key).text()
                                if (val != null && oldval.indexOf('World') == -1) {
                                    $("#dynamicinputlabel"+key).append("<span class='dynamicinput'>["+String(val)+"]</span>")
                                }
                            })
                            
                        }
                    }));

                    var getting_desciptions = $.when(getting_drivers).then($.ajax({url: "/uihandler",
                        data: {"statevar":"drivers_descriptions"},type:"GET",
                        success: function(json){
                            //Put the driver units on the labels
                            $.each(json['drivers_descriptions'],function(key,val){
                                $cblog(5,e,"Description for "+String(key)+"is "+String(val))
                                if (val != null) {
                                    $("#dynamicinputlabel"+key).attr("title",String(val))
                                }
                            })
                            
                        }
                    }));

                    $.when(getting_units,getting_desciptions).done(all_done.resolve);
                } else {
                    $cblog(4,e,"Drivers not set to reinit, resolving main Deferred")
                    all_done.resolve()
                }
                return all_done.promise()
            })

            //-------------------------------------------------            
            //BUTTON CALLBACKS
            //-------------------------------------------------

            //Handle clicking the previous or next button


            $("#previous_button").on("click",function(e) {
                e.preventDefault();
                $cblog(5,e,"In callback")
                var prevdone = $.Deferred()
                //Put in the loading sign
                $("#plotimg").attr("src","/www/loading.gif").fadeIn(200)

                var getting_prev = $.ajax({url: "/uihandler", data: {"posttype":"prevplot"},type: "POST",
                    success: function (json) {
                        $("#plotimg").attr("src",json["plot"]).fadeIn(400);
                        $("#plotimg_cap").html($format_caption(json["caption"]));
                        
                        $cblog(4,e,"previous: img: "+json["plot"]+"ind: "+String(json["ind"])+"len(controlstatemanger.states)="+String(json["maxind"]))
                                    
                        $("#caplabel").text('Plot #'+json["ind"]+'/'+json["maxind"])
                        $("#dynamicdriverdiv").addClass('initialize_me')
                        $driver_reinit = true
                    },
                    error: function (jqxhr) {

                        $cblog(1,e,"FAILED to AJAX in previous plot url, caption, index, response was: "+jqxhr.responseText)
                        alert("Sorry, I couldn't retrieve previous plot")
                        $("#plotimg").attr("src","/www/error.png").fadeIn(200)
                    }

                });
                
                $.when(getting_prev)
                .then(function () {
                    if (debug) {console.log("Now triggering dynamicdriverdiv click handler from prev plot callback")}
                    return $("#dynamicdriverdiv").triggerHandler("click")
                    })
                .then($("#driverchart").triggerHandler('focus'))
                .then($.when_all_trigger($all_controls,"focus"))
                .then($init_sel('all'))
                .done(function (f) {
                    $cblog(4,e,"Done with previous, resolving")
                    prevdone.resolve()
                    return prevdone.promise()
                })

                return prevdone.promise()
            })

            $("#next_button").on("click",function(e) {
                e.preventDefault();
                $cblog(5,e,"In callback")
                //Put in the loading sign
                var nextdone = $.Deferred()
                $("#plotimg").attr("src","/www/loading.gif").fadeIn(200)

                var getting_next = $.ajax({url: "/uihandler", data: {"posttype":"nextplot"},type: "POST",
                    success: function (json) {
                        $("#plotimg").attr("src",json["plot"]).fadeIn(400);
                        $("#plotimg_cap").html($format_caption(json["caption"]));
                        $("#caplabel").text('Plot #'+json["ind"]+'/'+json["maxind"])
                        $("#dynamicdriverdiv").addClass('initialize_me')
                        $driver_reinit = true

                        $cblog(4,e,"next: img: "+json["plot"]+"ind: "+String(json["ind"])+"len(controlstatemanger.states)="+String(json["maxind"]))
                    },

                    error: function (jqxhr) {
                        $cblog(1,e,"FAILED to AJAX in nextplot plot url, caption, index, response was: "+jqxhr.responseText)
                        alert("Sorry, I couldn't retrieve next plot")
                        $("#plotimg").attr("src","/www/error.png").fadeIn(200)
                    }

                });

                $.when(getting_next)
                .then(function () {
                    if (debug) {console.log("Now triggering dynamicdriverdiv click handler from next plot callback")}
                    return $("#dynamicdriverdiv").triggerHandler("click")
                    })
                .then($("#driverchart").triggerHandler('focus'))
                .then($.when_all_trigger($all_controls,"focus"))
                .then($init_sel('all'))
                .done(function (f) {
                    $cblog(4,e,"Done with next, resolving")
                    nextdone.resolve()
                    return nextdone.promise()
                });

                return nextdone.promise()
            });
                
            
            //Some cute little animation of the plot details
            $("#plotimg").on('click', function() {

                $('#capdiv').slideToggle()
            })

            $("#capdiv").on('click', function() {
                $('#capdiv').slideUp()
            })

            //Bind a click handler to the panic button
            $("#restart").on("click",function(e) {
                e.preventDefault();
                var response = window.confirm("Really restart the backend? You will lose all your plots for this session!")
                if (response) {
                    $.ajax({url: "/uihandler", data: {"posttype":"restart"},type: "POST",
                        success: function (f) {
                          
                                window.location.reload(true)
                        }
                    })
                }
            });

            //Bind a click handler to the logout button
            $("#logout").on("click",function(e) {
                e.preventDefault();
                var response = window.confirm("Really log out? You will lose all your plots for this session!")
                if (response) {
                    $.ajax({url: "/uihandler", data: {"posttype":"logout"},type: "POST",
                        success: function (f) {
                          
                                window.location.replace("/login")
                        }
                    })
                }
            });

            //Bind a click handler to the logout button
            $("#help").on("click",function(e) {
                e.preventDefault();
                window.location.replace("/docs/index.html")
            });

            //Implement mutual exclusivity of drivers and dates
            $("#manualpanel_title").on("click", function (e){
                $("#manualpanel_title").text("Manual Driver Entry")
                var animating1 = $("#manualpanel_controls").slideDown()
                $("#datepanel_title").text("Click to Look Up Solar Activity By Date")
                var animating2 = $("#datepanel_controls").slideUp()
                var ajaxing = $.ajax({url: "/uihandler", data: {"statevar":"driver_lookup","newval":"False"},type: "PUT"})
                return $.when(animating2,animating1,ajaxing)
            })

            $("#datepanel_title").on("click", function (e){
                $("#manualpanel_title").text("Click to Specify Solar Activity Manually")
                var animating1 = $("#manualpanel_controls").slideUp()
                $("#datepanel_title").text("Date and Time")
                var animating2 = $("#datepanel_controls").slideDown()
                var ajaxing = $.ajax({url: "/uihandler", data: {"statevar":"driver_lookup","newval":"True"},type: "PUT"})
                return $.when(animating1,animating2,ajaxing)
            })

            //------------------------------------------------------------------------------------------------
            //
            //  END OF CALLBACKS, FROM HERE ON, WE ARE EXECUTING THE MAIN BODY OF THE PAGE LOAD / APP STARTUP
            //
            //------------------------------------------------------------------------------------------------


            //Put a loading image in the plot
            $("#capdiv").slideUp()
            $("#plotimg").attr("src","/www/loading.gif").fadeIn(200)

            //Ajax in the username and user info, we will wait for this and the backend synch POST to complete before 
            //doing anything else
            var getting_username = $.ajax({url: "/uihandler",data: {"statevar":"username"},type: "GET",dataType:"json",
                    success : function (json) {
                        var un = json["username"]
                        if ( un.length > 0 ) {
                            $("#username").text(un)
                        } else {
                            window.location.replace('/login')
                        }  
                    }
                })
            
            //Add to the starting up deferred
            getting_username.done(starting_up.notify('Getting user info...',5))

            //Signal to the uihandler that we're ready to sync up the contolstate to the session
            //we currently don't use this feature for anything, it could probably be removed TODO
            
            //Chain together synching and getting_username, remember that .then returns another deferred (or maybe a promise?)
            var synching = getting_username.then($.ajax({url: "/uihandler", data: {"posttype":"uiready"},type: "POST"}))
            //synching is a 'Promise'...a read-only Deferred
            synching.done(starting_up.notify('Syncing...(if this seems to take forever, try refreshing the browser)',20))
            
            //--Set initial plot
            var initial_plot = $.when(synching).then(function (thedata) {
                var success_done = $.Deferred()
                $logit(3,"synching.done"," uiready POST has been sent and completed")

                var plotting_done = $.ajax({url: "/uihandler", data: {"posttype":"replotnow"},type: "POST",dataType: "json",
                    success: function( json ) {
                        starting_up.notify('First plot made...',70)
                        $logit(4,"syching.done: AJAX: POST:replotnow: success"," Beginning intialization $.then chain")
                        //These must be done in the right order, so I chain a bunch of then() calls 
                        //each of which returns a promise 

                        //They must be done in order because they tell the x,y,and z
                        //selectors to populate and set up the proper visibility for the position 
                        //elements based on the plottype that is default in the controlstate
                        //resolve when the success function has finished
                        //Now we chain together all of the callbacks 
                        $.when($plottype_sel.triggerHandler("focus"))
                            .then(function (thedat) {
                                    $logit(4,"syching.done: AJAX: POST:replotnow : success","Done with plottype focus")
                                    return $.when($plottype_sel.triggerHandler("change"))
                                })
                            .then(function (data) {
                                    $logit(4,"syching.done: AJAX: POST:replotnow : success","Done with plottype change") 
                                    var xdone = $xvar_sel.triggerHandler("focus")
                                    var ydone = $yvar_sel.triggerHandler("focus")
                                    var zdone = $zvar_sel.triggerHandler("focus")
                                    return $.when(xdone,ydone,zdone).then($.when_all_trigger('.positioninput,.dateinput',"focus"));
                                })
                            .then(function (thedata) {
                                    $logit(4,"syching.done: AJAX: POST:replotnow : success","Now trigger bounds focus")
                                    //trigger all bounds to refresh
                                    return $.when_all_trigger($all_var_bounds,"focus")
                                })
                            .then($("#dynamicdriverdiv").triggerHandler("click"))
                            .then($("#datepanel_title").triggerHandler("click"))
                            .done(
                                function (stuff) {
                                //Very last thing we do is take away the loading gif
                                //and update the plot
                                starting_up.notify('UI Refreshed!',75)
                                $logit(4,"syching.done: AJAX: POST:replotnow : success","Now remove loading gif and put in img and caption")        
                                $("#plotimg").attr("src",json["src"]);    
                                $("#plotimg_cap").html($format_caption(json["cap"]))
                                $show_controls()})
                            .done(success_done.resolve)
                        
                    }
                        
                });
                

                return success_done.promise() 
            })
            //When we have the controls properly setup initially, make 
            //sure that the position inputs are setup correctly,
            //and that the dynamic drivers chart has been updated
            initial_plot.done($hidePosIfNeeded,$("#driverchart").triggerHandler('focus')) 

            

            

            //Bind a change handler to the username field
            //$("#username").on("change",function(e) {
                //e.preventDefault();
            //    $cblog(5,e,"In callback")
            //    var myname = $(e.target).attr("name")
            //     var newun = $(e.target).val()
            //     //Use the name attr of the input to decide what field of the datetime object we will get
                
            //     var donesetting = $.ajax({url: "/uihandler",data: {"statevar":myname,"newval":newun},type: "PUT",dataType:"json",
            //         success: function(json) {
            //             $cblog(3,e,"Username set to: "+newun)
            //         }
            //     })

            //     var doneprocessing = $.when(donesetting).then(
            //         $.ajax({url: "/uihandler",data: {"statevar":myname},type: "GET",dataType:"json",
            //             success: function(json) {
            //                 $cblog(3,e,"Username read is:"+json[myname])
            //                 alert("Welcome to AtModWeb, "+String(json[myname]))
            //             } 
            //         })
            //     )
            //     return doneprocessing
            // })
                
            $("#putnewval").on("change",function(e) {
                var newstatevar = $("#putstatevar").val()
                var newvalue = $("#putnewval").val()
                var dangerous = $.ajax({url: "/uihandler", data: {"statevar":newstatevar,"newval":newvalue},type: "PUT",dataType: "json"})
                return dangerous.done($("#plotbutton").triggerHandler("click"))
            })

            //Bind a click handler to the debug panel to hide it on click, or initialize it if nessecary
            //$("#debugpanel").on('click',function(e) {
            //    $cblog(5,e,"In callback")
            //    if ( $("#debugpanel").hasClass("debug_on") ) {
            //        $("#debugpanel").removeClass("debug_on")
            //        $("#debug_table,#panic").slideUp()
            //    } else {
            //        $("#debugpanel").addClass("debug_on")
            //        $("#debug_table,#panic").slideDown()
            //    }
            //    if ( $("#debugpanel").hasClass("debug_on") ) {
            //        $.ajax({url: "/uihandler",data: {"statevar":"controlstate"},type:"GET",
            //            success: function(json) {
            //                if ( $("#debugpanel").hasClass("initialize_me") ){
            //                    $("#debugpanel").append($("<table>").attr("ID","debug_table")).addClass('debug_table')
            //                    $("#debugpanel").removeClass("initialize_me")
            //                }

            //                $(".debug_table_el").remove() //Clear old
            //                $.each(json["controlstate"],function(key,value) {
            //                    //console.log(value)
            //                    $("#debug_table").prepend(
            //                        $("<tr>").append(
            //                            $("<th>").append($("<strong>").text(key)).addClass('debug_table_el').addClass('debug'+key),
            //                            $("<td>").html($.parseHTML(value)).addClass('debug_table_el').addClass('debug'+key)
            //                        )
            //                    ).addClass('debug_table')
            //                });
            //                //Make sure all of that class adding was processed
            //                $('.debug_table_el')
            //            }
            //
            //        });
            //   } else {
            //        $("#debug_table,#panic").hide()
            //    }
            //}); 

            
        });

        $(document).keypress(function(e) {
            console.log("keypress id = "+e.which)
            if(e.which == 68) {
                // D pressed
                $(".debug").toggle()
            }
            if(e.which == 77) {
                // M press
                $(".model").toggle()
            }
            if(e.which == 71) {
                //G press
                var gif_mode_on = $.ajax({url: "/uihandler", data: {"posttype":"gifmode"},type: "POST",
                    success: function(json) {
                            if ( !json['gifmode'] ) {
                                window.location.replace(json['file'])
                            } else {
                                alert('Beginning GIF animation compilation. Any further plots will be added to GIF, until you press Shift+G, which will take you to your GIF')    
                            }                            
                        }
                    })

            }
        });
        

//        $(document).on("click", function (e){
            //This is a hack to get the position controls to hide properly. I have no idea why it's not 
            //working with deferreds as I had hoped. Arg.
//           
//        });