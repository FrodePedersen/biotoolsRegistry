from django.core.management.base import BaseCommand, CommandError
from elasticsearch import Elasticsearch
from elixir.models import *
from xml.dom import minidom
import json, os


def f(node, term):
	if len(term) > 0:
		if node['data']['uri'] == term:
			return node
		else:
			if len(node['children']) > 0:
				for child in node['children']:
					n = f(child, term)
					if n is not None:
						return n
			else:
				return None
	return None


def getNode(node, name):
	if len(name) > 0:
		if node['text'] == name:
			return node
		else:
			if len(node['children']) > 0:
				for child in node['children']:
					n = getNode(child, name)
					if n is not None:
						return n
			else:
				return None
	return None


def getName(node):
	for n2 in node.childNodes:
		if n2.nodeName == 'rdfs:label':
			return n2.firstChild.nodeValue


def getRemoved(node):
	number = 0
	for el in node:
		if el['remove'] == 1:
			number = number + 1
	return number


def flatten(lst, node, prev):
	tmp = {}
	tmp['definition'] = ''
	tmp['path'] = ''
	tmp['name'] = node['text']
	if prev == '':
		tmp['path'] = node['text']
	else:
		tmp['path'] = prev + '//' + node['text']
	if 'definition' in node:
		tmp['definition'] = node['definition']
	tmp['uri'] = node['data']['uri']
	lst.append(tmp)
	if len(node['children']) > 0:
		for child in node['children']:
			flatten(lst, child, tmp['path'])
	return None


def listify(input_list):
	obj_list = []
	for el in input_list:
		node = el['node']
		if node.hasChildNodes() and el['remove'] == 0:
			if node.attributes:
				attrs = {}
				attrs['text'] = ''
				attrs['data'] = {}
				attrs['definition'] = ''
				attrs['data']['uri'] = ''
				attrs['parents'] = []
				attrs['used_parents'] = []
				attrs['remove'] = 0
				attrs['children'] = []
				attrs['exact_synonyms'] = []
				attrs['narrow_synonyms'] = []
				attrs['replaced_by'] = []
				attrs['consider'] = []
				for n2 in node.childNodes:
					if n2.nodeName == 'rdfs:label':
						attrs['text'] = n2.firstChild.nodeValue
						attrs['data']['uri'] = node.attributes['rdf:about'].value
					if n2.nodeName == 'rdfs:subClassOf' and n2.attributes:
						attrs['parents'].append(n2.attributes['rdf:resource'].value)
					if n2.nodeName == 'oboInOwl:hasExactSynonym' and n2.firstChild:
						attrs['exact_synonyms'].append(n2.firstChild.nodeValue)
					if n2.nodeName == 'oboInOwl:hasNarrowSynonym' and n2.firstChild:
						attrs['narrow_synonyms'].append(n2.firstChild.nodeValue)
					if n2.nodeName == 'oboInOwl:replacedBy' and n2.attributes['rdf:resource'].value:
						attrs['replaced_by'].append(n2.attributes['rdf:resource'].value)
					if n2.nodeName == 'oboInOwl:consider' and n2.attributes['rdf:resource'].value:
						attrs['consider'].append(n2.attributes['rdf:resource'].value)
					if n2.nodeName == 'oboInOwl:hasDefinition':
						attrs['definition'] = n2.firstChild.nodeValue
				obj_list.append(attrs)
				el['remove'] = 1
	return obj_list


def treefy(node, o):
	for el in o:
		for parent in el['parents']:
			if node['data']['uri'] == parent:
				exists = False
				for ch in node['children']:
					if ch['data']['uri'] == el['data']['uri']:
						exists = True
				if not exists:
					node['children'].append({'text':el['text'], 'data':{'uri':el['data']['uri']}, 'children': [], 'exact_synonyms': el['exact_synonyms'], 'narrow_synonyms': el['narrow_synonyms'], 'replaced_by': el['replaced_by'], 'consider': el['consider'], 'definition': el['definition']})
	for ch in node['children']:
		treefy(ch, o)


def ontology_save(name, data, path_edam_json, version):

	# data -> tree of the ontology
	# flat_data -> flattened tree
	flat_data = []
	flatten(flat_data, data, '')
	for el in flat_data:
		if el['definition'] == '' and el['name'] == '' and el['uri'] == '':
			flat_data.remove(el)
	flat_data_json = json.dumps(flat_data)

	with open(path_edam_json + '/current/' + name + '.json', 'w') as outfile:
		json.dump(data, outfile)
	with open(path_edam_json + '/current/flat_' + name + '.json', 'w') as outfile:
		json.dump(flat_data, outfile)

	with open(path_edam_json + '/' + version + '/' + name + '_' + version + '.json', 'w') as outfile:
		json.dump(data, outfile)
	with open(path_edam_json + '/' + version + '/flat_' + name + '_' + version + '.json', 'w') as outfile:
		json.dump(flat_data, outfile)


	ontology_structure_json = json.dumps(data)
	flat_data_structure_json = json.dumps(flat_data)
	# populating a fresh DB 'current'
	query = Ontology.objects.filter(name__exact=name)
	if len(query) == 0:
		o = Ontology(name=name, data=ontology_structure_json)
		o.save()
	# updating records
	elif len(query) == 1:
		o = query[0]
		o.data = json.dumps(data)
		o.save()
	else:
		self.stdout.write('ERROR PARSING ' + name)

	# populating a DB with version EDAM
	query = Ontology.objects.filter(name__exact=name + '_' + version)
	if len(query) == 0:
		o = Ontology(name=name + '_' + version, data=ontology_structure_json)
		o.save()
	# updating records
	elif len(query) == 1:
		o = query[0]
		o.data = json.dumps(data)
		o.save()
	else:
		self.stdout.write('ERROR PARSING ' + name + '_' + version)

	# populating a fresh DB 'current'
	query = Ontology.objects.filter(name__exact='flat_' + name)
	if len(query) == 0:
		o = Ontology(name='flat_' + name, data=flat_data_structure_json)
		o.save()
	# updating records
	elif len(query) == 1:
		o = query[0]
		o.data = json.dumps(data)
		o.save()
	else:
		self.stdout.write('ERROR PARSING ' + 'flat_' + name)

	# populating a DB with version EDAM
	query = Ontology.objects.filter(name__exact='flat_' + name + '_' + version)
	if len(query) == 0:
		o = Ontology(name='flat_' + name + '_' + version, data=flat_data_structure_json)
		o.save()
	# updating records
	elif len(query) == 1:
		o = query[0]
		o.data = json.dumps(data)
		o.save()
	else:
		self.stdout.write('ERROR PARSING ' + name + '_' + version)


class Command(BaseCommand):
	help = 'Regenerate the EDAM ontology'

	def handle(self, *args, **options):
		version = ''
		path_edam_data = '/elixir/application/backend/data/edam'
		with open(path_edam_data + '/current_version.txt') as f:
			version = f.read().strip('\n')
		path_edam_json = path_edam_data + '/json'

		self.stdout.write('------------------------------------')
		self.stdout.write('Regenerating the EDAM version '+ version)

		xmldoc = minidom.parse(path_edam_data + '/owl/EDAM_' + version + '.owl')
		il = xmldoc.getElementsByTagName('owl:Class')

		topic_list = []
		operation_list = []
		data_list = []
		format_list = []
		obsolete_list = []

		for el in il:
			marker = None
			try:
				marker = el.attributes['rdf:about'].nodeValue
			except:
				marker = None
				continue
			if marker is not None:
				if 'http://edamontology.org/' in marker:
					obsolete = False
					for n in el.childNodes:
						if n.nodeName == 'rdfs:subClassOf' and n.attributes and not obsolete:
							if n.attributes['rdf:resource'].value == 'http://www.w3.org/2002/07/owl#DeprecatedClass':
								obsolete = True
					if obsolete:
						obsolete_list.append({'remove':0,'node':el})
					else:
						if 'http://edamontology.org/topic_' in marker:
							topic_list.append({'remove':0,'node':el})
						elif 'http://edamontology.org/operation_' in marker:
							operation_list.append({'remove':0,'node':el})
						elif 'http://edamontology.org/data_' in marker:
							data_list.append({'remove':0,'node':el})
						elif 'http://edamontology.org/format_' in marker:
							format_list.append({'remove':0,'node':el})

		obsolete_tree = {
			'text': 'Deprecated',
			'data': {
				'uri': 'http://www.w3.org/2002/07/owl#DeprecatedClass'
			},
			'children': []
		}
		treefy(obsolete_tree, listify(obsolete_list))
		
		topic_tree = {
			'text': 'Topic',
			'data': {
				'uri': 'http://edamontology.org/topic_0003'
			},
			'children': []
		}
		treefy(topic_tree, listify(topic_list))

		operation_tree = {
			'text': 'Operation',
			'data': {
				'uri': 'http://edamontology.org/operation_0004'
			},
			'children': []
		}
		treefy(operation_tree, listify(operation_list))

		data_tree = {
			'text': 'Data',
			'data': {
				'uri': 'http://edamontology.org/data_0006'
			},
			'children': []
		}
		treefy(data_tree, listify(data_list))

		format_tree = {
			'text': 'Format',
			'data': {
				'uri': 'http://edamontology.org/format_1915'
			},
			'children': []
		}
		treefy(format_tree, listify(format_list))


		############################### Dirs
		# version folder
		if not os.path.exists(path_edam_json + '/' + version):
			os.makedirs(path_edam_json + '/' + version)
		
		if not os.path.exists(path_edam_json + '/current'):
			os.makedirs(path_edam_json + '/current')

		############################### Topic
		ontology_save('EDAM_Topic', topic_tree, path_edam_json, version)
		self.stdout.write('Topic saved.')

		############################### Operation
		ontology_save('EDAM_Operation', operation_tree, path_edam_json, version)
		self.stdout.write('Operation saved.')

		############################### Data
		ontology_save('EDAM_Data', data_tree, path_edam_json, version)
		self.stdout.write('Data saved.')

		############################### Format
		ontology_save('EDAM_Format', format_tree, path_edam_json, version)
		self.stdout.write('Format saved.')

		############################### Obsolete
		ontology_save('EDAM_obsolete', obsolete_tree, path_edam_json, version)
		self.stdout.write('Obsolete saved.')


		self.stdout.write('All done.')
