#!/usr/bin/env python
#
# Copyright (c) 2010-2012 Appcelerator, Inc. All Rights Reserved.
# Licensed under the Apache Public License (version 2)

import os, sys, re

this_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(this_dir, "..")))

from common import dict_has_non_empty_member, strip_tags, not_real_titanium_types, to_ordered_dict

android_support_dir = os.path.abspath(os.path.join(this_dir, "..", "..", "support", "android"))
sys.path.append(android_support_dir)

# We package markdown and simplejson in support/common.
common_support_dir = os.path.abspath(os.path.join(this_dir, "..", "..", "support", "common"))
sys.path.append(common_support_dir)
from markdown import markdown

from tilogger import *
log = None
all_annotated_apis = None

try:
	import json
except:
	import simplejson as json

def markdown_to_html(s):
	# When Ti Studio starts using a rich control for displaying code assist free text
	# (which they're planning, according to Kevin Lindsey), we can start doing more
	# with this like coming up with ways to link to other types.  For now the free-form
	# text goes straight is as html generated by markdown.  They strip out tags.
	# Discussed with Kevin 8/19/2011.
	html = markdown(s)
	# Any <Titanium.XX.XX> type of markdown links need to have their brackets removed so
	# the code assist doesn't see them as tags and thus strip them, thereby losing the
	# useful text within.  Same for known pseudo-types.
	pattern = r"\<[^\>\s]+\>"
	matches = re.findall(pattern, html)
	if matches:
		for m in matches:
			tag_name = m[1:-1]
			if tag_name.startswith("Titanium") or tag_name in all_annotated_apis:
				html = html.replace(m, tag_name)
	return html

# Fixes illegal names like "2DMatrix" (not valid Javascript name)
def clean_namespace(ns_in):
	def clean_part(part):
		if len(part) and part[0].isdigit():
			return "_" + part
		else:
			return part
	return ".".join([clean_part(s) for s in ns_in.split(".") ])

# Do not prepend 'Global' to class names (TIDOC-860)
def clean_class_name(class_name):
	if class_name.startswith('Global.'):
		return class_name[7:]
	else:
		return class_name

def build_deprecation_message(api):
	# Returns the message in markdown format.
	result = None
	if api.deprecated:
		result = "  **Deprecated"
		if api.deprecated.has_key("since"):
			result += " since %s." % api.deprecated["since"]
		if api.deprecated.has_key("removed"):
			result += " Removed in %s." % api.deprecated["removed"]
		if api.deprecated.has_key("notes"):
			result += " %s" % api.deprecated["notes"]
		result += "**"
	return result

def to_jsca_description(summary, api=None):
	if summary is None:
		return ""
	new_summary = summary
	if api is not None and api.deprecated is not None:
		deprecation_message = build_deprecation_message(api)
		if deprecation_message is not None:
			new_summary += deprecation_message
	return markdown_to_html(new_summary)

def to_jsca_example(example):
	return {
			"name": example["title"],
			"code": markdown_to_html(example["example"])
			}

def to_jsca_examples(api):
	if dict_has_non_empty_member(api.api_obj, "examples"):
		return [to_jsca_example(example) for example in api.api_obj["examples"]]
	else:
		return []

def to_jsca_inherits(api):
	if dict_has_non_empty_member(api.api_obj, "extends"):
		return api.api_obj["extends"]
	else:
		return 'Object'

def to_jsca_permission(prop):
	if dict_has_non_empty_member(prop.api_obj, "permission"):
		return prop.api_obj["permission"]
	else:
		return "read-write"

def to_jsca_availability(prop):
	if dict_has_non_empty_member(prop.api_obj, "availability"):
		return prop.api_obj["availability"]
	else:
		return "always"

def to_jsca_type_name(type_info):
	if isinstance(type_info, list) or isinstance(type_info, tuple) and len(type_info) > 0:
		# Currently the JSCA spec allows for just one type per parameter/property/returnType.
		# We have to choose one.
		# We'll take "Object" if it's one of the possible types, else we'll just take the first one.
		if "object" in [t.lower() for t in type_info]:
			return "Object"
		else:
			return to_jsca_type_name(type_info[0])
	type_test = type_info
	if type_test.startswith("Callback"):
		type_test ="Function"
	elif type_test.startswith("Array"):
		type_test = "Array"
	# for jsca we're setting Dictionary<XX> to just XX as we did in the old jsca generator when
	# setting the parameter type of createXX methods to XX in order to get rich documentation
	# for what's expected in that parameter.
	elif type_test.startswith("Dictionary<"):
		match = re.findall(r"<([^>]+)>", type_test)
		if match is not None and len(match) > 0:
			type_test = match[0]
	elif type_test == "Dictionary":
		type_test = "Object"
	return clean_namespace(type_test)

def to_jsca_constants(constants_list):
	global all_annotated_apis
	rv = []
	if type(constants_list) is not list:
		a = [constants_list]
		constants_list = a
	for item in constants_list:
		namespace = item.rsplit('.', 1)[0]
		token = item.rsplit('.', 1)[-1]
		if item[-1] == '*':
			token = token[:-1]

		if namespace in all_annotated_apis:
			for property in all_annotated_apis[namespace].api_obj["properties"]:
				if (token and property["name"].startswith(token)) or (not token and re.match(r"[_A-Z]+", property["name"])):
					rv.append(namespace + "." + property["name"])
				if property["name"] == token:
					break
	return rv



def to_jsca_property(prop, for_event=False):
	result = {
			"name": prop.name,
			"description": "" if "summary" not in prop.api_obj else to_jsca_description(prop.api_obj["summary"], prop),
			"deprecated": prop.deprecated is not None and len(prop.deprecated) > 0,
			"type": "" if "type" not in prop.api_obj else to_jsca_type_name(prop.api_obj["type"])
			}
	if not for_event:

		creatable = False;
		if dict_has_non_empty_member(prop.parent.api_obj, "extends"):
			ancestor = prop.parent.api_obj["extends"]
			if (ancestor == "Titanium.Proxy" or ancestor == "Titanium.UI.View"):
				creatable = True
			if ("createable" in prop.parent.api_obj):
				creatable = prop.parent.api_obj["createable"]

		result["isClassProperty"] = False if (creatable and prop.name != prop.name.upper()) else True
		result["isInstanceProperty"] = True if (creatable and prop.name != prop.name.upper()) else False
		result["since"] = to_jsca_since(prop.platforms)
		result["userAgents"] = to_jsca_userAgents(prop.platforms)
		result["isInternal"] = False
		result["examples"] = to_jsca_examples(prop)
		result["availability"] = to_jsca_availability(prop)
		result["permission"] = to_jsca_permission(prop)
	if "constants" in prop.api_obj:
		result["constants"] = to_jsca_constants(prop.api_obj["constants"])
	return to_ordered_dict(result, ("name",))

def to_jsca_properties(props, for_event=False):
	return [to_jsca_property(prop, for_event) for prop in props]

def to_jsca_return_types(return_types):
	if return_types is None or len(return_types) == 0:
		return []
	orig_types = return_types
	if not isinstance(orig_types, list):
		orig_types = [orig_types]
	return [{
		"type": to_jsca_type_name(t["type"]),
		"description": "" if "summary" not in t else to_jsca_description(t["summary"])
		} for t in orig_types]

def to_jsca_method_parameter(p):
	data_type = to_jsca_type_name(p.api_obj["type"])
	if data_type.lower() == "object" and p.parent.name.startswith("create"):
		if "returns" in p.parent.api_obj:
			method_return_type = p.parent.api_obj["returns"]["type"]
			if method_return_type in all_annotated_apis:
				type_in_method_name = p.parent.name.replace("create", "")
				if len(type_in_method_name) > 0 and type_in_method_name == method_return_type.split(".")[-1]:
					data_type = to_jsca_type_name(method_return_type)
	usage = "required"

	if "optional" in p.api_obj and p.api_obj["optional"]:
		usage = "optional"
	elif p.repeatable:
		usage = "one-or-more"

	result = {
			"name": p.name,
			"description": "" if "summary" not in p.api_obj else to_jsca_description(p.api_obj["summary"], p),
			"type": data_type,
			"usage": usage
			}
	if "constants" in p.api_obj:
		result["constants"] = to_jsca_constants(p.api_obj["constants"])
	return to_ordered_dict(result, ('name',))

def to_jsca_function(method):
	log.trace("%s.%s" % (method.parent.name, method.name))

	creatable = False;
	if dict_has_non_empty_member(method.parent.api_obj, "extends"):
		ancestor = method.parent.api_obj["extends"]
		if (ancestor == "Titanium.Proxy" or ancestor == "Titanium.UI.View"):
			creatable = True;
	if ("createable" in method.parent.api_obj):
		creatable = method.parent.api_obj["createable"]

	result = {
			"name": method.name,
			"deprecated": method.deprecated is not None and len(method.deprecated) > 0,
			"description": "" if "summary" not in method.api_obj else to_jsca_description(method.api_obj["summary"], method)
			}
	if dict_has_non_empty_member(method.api_obj, "returns") and method.api_obj["returns"] != "void":
		result["returnTypes"] = to_jsca_return_types(method.api_obj["returns"])
	if method.parameters is not None and len(method.parameters) > 0:
		result["parameters"] = [to_jsca_method_parameter(p) for p in method.parameters]
	result["since"] = to_jsca_since(method.platforms)
	result['userAgents'] = to_jsca_userAgents(method.platforms)
	result['isInstanceProperty'] = True if creatable else False
	result['isClassProperty'] = False if creatable else True
	result['isInternal'] = False # we don't make this distinction (yet anyway)
	result['examples'] = to_jsca_examples(method)
	result['references'] = [] # we don't use the notion of 'references' (yet anyway)
	result['exceptions'] = [] # we don't specify exceptions (yet anyway)
	result['isConstructor'] = False # we don't expose native class constructors
	result['isMethod'] = True # all of our functions are class instance functions, ergo methods
	return to_ordered_dict(result, ('name',))

def to_jsca_functions(methods):
	return [to_jsca_function(method) for method in methods]

def to_jsca_event(event):
	return to_ordered_dict({
			"name": event.name,
			"description": "" if "summary" not in event.api_obj else to_jsca_description(event.api_obj["summary"], event),
			"deprecated": event.deprecated is not None and len(event.deprecated) > 0,
			"properties": to_jsca_properties(event.properties, for_event=True)
			}, ("name",))

def to_jsca_events(events):
	return [to_jsca_event(event) for event in events]

def to_jsca_remarks(api):
	if dict_has_non_empty_member(api.api_obj, "description"):
		return [markdown_to_html(api.api_obj["description"])]
	else:
		return []

def to_jsca_userAgents(platforms):
	return [{"platform": platform["name"]} for platform in platforms]

def to_jsca_since(platforms):
	return [to_ordered_dict({
		"name": "Titanium Mobile SDK - %s" % platform["pretty_name"],
		"version": platform["since"]
		}, ("name",)) for platform in platforms]

def to_jsca_type(api):
	# Objects marked as external should be ignored
	if api.external:
		return None
	if api.name in not_real_titanium_types:
		return None
	log.trace("Converting %s to jsca" % api.name)
	result = {
			"name": clean_class_name(clean_namespace(api.name)),
			"isInternal": False,
			"description": "" if "summary" not in api.api_obj else to_jsca_description(api.api_obj["summary"], api),
			"deprecated": api.deprecated is not None and len(api.deprecated) > 0,
			"examples": to_jsca_examples(api),
			"properties": to_jsca_properties(api.properties),
			"functions": to_jsca_functions(api.methods),
			"events": to_jsca_events(api.events),
			"remarks": to_jsca_remarks(api),
			"userAgents": to_jsca_userAgents(api.platforms),
			"since": to_jsca_since(api.platforms),
			"inherits": to_jsca_inherits(api)
			}
	# TIMOB-7169. If it's a proxy (non-module) and it has no "class properties",
	# mark it as internal.  This avoids it being displayed in Code Assist.
	# TIDOC-860. Do not mark Global types as internal.
	if api.typestr == "proxy" and not (api.name).startswith('Global.'):
		can_hide = True
		for p in result["properties"]:
			if p["isClassProperty"]:
				can_hide = False
				break
		result["isInternal"] = can_hide
	return to_ordered_dict(result, ('name',))

def generate(raw_apis, annotated_apis, options):
	global all_annotated_apis, log
	log_level = TiLogger.INFO
	if options.verbose:
		log_level = TiLogger.TRACE
	all_annotated_apis = annotated_apis
	log = TiLogger(None, level=log_level, output_stream=sys.stderr)
	log.info("Generating JSCA")
	result = {'aliases': [ {'name': 'Ti', 'type': 'Titanium'} ]}
	types = []
	result['types'] = types

	for key in all_annotated_apis.keys():
		jsca_type = to_jsca_type(all_annotated_apis[key])
		if jsca_type is not None:
			types.append(jsca_type)

	if options.stdout:
		json.dump(result, sys.stdout, sort_keys=False, indent=4)
	else:
		output_folder = None
		if options.output:
			output_folder = options.output
		else:
			dist_dir = os.path.abspath(os.path.join(this_dir, "..", "..", "dist"))
			if os.path.exists(dist_dir):
				output_folder = os.path.join(dist_dir, "apidoc")
				if not os.path.exists(output_folder):
					os.mkdir(output_folder)
		if not output_folder:
			log.warn("No output folder specified and dist path does not exist.  Forcing output to stdout.")
			json.dump(result, sys.stdout, sort_keys=False, indent=4)
		else:
			output_file = os.path.join(output_folder, "api.jsca")
			f = open(output_file, "w")
			json.dump(result, f, sort_keys=False, indent=4)
			f.close()
			log.info("%s written" % output_file)
