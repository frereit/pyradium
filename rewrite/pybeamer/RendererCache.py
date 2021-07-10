#	pybeamer - HTML presentation/slide show generator
#	Copyright (C) 2021-2021 Johannes Bauer
#
#	This file is part of pybeamer.
#
#	pybeamer is free software; you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation; this program is ONLY licensed under
#	version 3 of the License, later versions are explicitly excluded.
#
#	pybeamer is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	You should have received a copy of the GNU General Public License
#	along with pybeamer; if not, write to the Free Software
#	Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#	Johannes Bauer <JohannesBauer@gmx.de>

import os
import contextlib
import hashlib
import datetime
import collections
import json
from .ExtendedJSONEncoder import ExtendedJSONEncoder

RenderedResult = collections.namedtuple("RenderedResult", [ "key", "keyhash", "from_cache", "data" ])

class BaseRenderer():
	@property
	def name(self):
		raise NotImplementedError(__class__.__name__)

	@property
	def properties(self):
		return { "version": 0 }

	def render(self, property_dict):
		raise NotImplementedError(__class__.__name__)

class RendererCache():
	def __init__(self, renderer):
		self._renderer = renderer
		self._directory = os.path.expanduser("~/.cache/pybeamer/" + self._renderer.name + "/")
		with contextlib.suppress(FileExistsError):
			os.makedirs(self._directory)

	@staticmethod
	def _hash_key(key):
		binkey = ExtendedJSONEncoder.dumps(key, minify = True, sort_keys = True).encode("utf-8")
		keyhash = hashlib.md5(binkey).hexdigest()
		return keyhash

	def _retrieve(self, keyhash):
		filename = self._directory + keyhash + ".json"
		try:
			with open(filename) as f:
				file_representation = ExtendedJSONEncoder.load(f)
		except (FileNotFoundError, json.decoder.JSONDecodeError):
			return None

		return RenderedResult(key = file_representation["key"], keyhash = keyhash, from_cache = True, data = file_representation["object"])

	def _store(self, key, keyhash, object_data):
		file_representation = {
			"key":		key,
			"meta": {
				"rendered":	datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
				"keyhash":	keyhash,
			},
			"object": object_data,
		}

		filename = self._directory + keyhash + ".json"
		with open(filename, "w") as f:
			ExtendedJSONEncoder.dump(file_representation, f, minify = True)

	def render(self, property_dict):
		key = {
			"name":						self._renderer.name,
			"renderer_properties":		self._renderer.properties,
			"object_properties":		property_dict,
		}
		keyhash = self._hash_key(key)
		cached_object = self._retrieve(keyhash)
		if cached_object is not None:
			return cached_object
		else:
			object_data = self._renderer.render(property_dict)
			self._store(key, keyhash, object_data)
			return RenderedResult(key = key, keyhash = keyhash, from_cache = False, data = object_data)

if __name__ == "__main__":
	class DebugRenderer(BaseRenderer):
		@property
		def name(self):
			return "debug"

		@property
		def properties(self):
			return { "version": 1 }

		def render(self, property_dict):
			return {
				"text":		property_dict["letter"] * property_dict["count"],
				"bytes":	b"foobar" * 1000,
			}

	cache = RendererCache(DebugRenderer())
	print("Result = ", cache.render({
		"letter":	"Q",
		"count":	10,
	}))
