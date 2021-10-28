#	pyradium - HTML presentation/slide show generator
#	Copyright (C) 2015-2021 Johannes Bauer
#
#	This file is part of pyradium.
#
#	pyradium is free software; you can redistribute it and/or modify
#	it under the terms of the GNU General Public License as published by
#	the Free Software Foundation; this program is ONLY licensed under
#	version 3 of the License, later versions are explicitly excluded.
#
#	pyradium is distributed in the hope that it will be useful,
#	but WITHOUT ANY WARRANTY; without even the implied warranty of
#	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#	GNU General Public License for more details.
#
#	You should have received a copy of the GNU General Public License
#	along with pyradium; if not, write to the Free Software
#	Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#	Johannes Bauer <JohannesBauer@gmx.de>

import json
import tempfile
import subprocess
import logging
import collections
from pyradium.RendererCache import BaseRenderer
from pyradium.CmdlineEscape import CmdlineEscape

_log = logging.getLogger(__spec__.name)

_TEX_TEMPLATE = r"""
\documentclass[preview,border=1mm,varwidth=true]{standalone}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage{amsmath}
\usepackage{amssymb}
\begin{document}
%(content)s
\end{document}
"""

class LatexFormulaRenderer(BaseRenderer):
	_DEBUG = False
	_Baseline = collections.namedtuple("Baseline", [ "image_width", "image_height", "upper", "lower", "mid" ])

	def __init__(self, rendering_dpi = 600):
		super().__init__()
		self._rendering_dpi = rendering_dpi

	@property
	def name(self):
		return "latex"

	@property
	def properties(self):
		return {
			"version":			3,
			"rendering_dpi":	self._rendering_dpi,
		}

	def _get_baseline_info(self, png_filename, xoffset):
		# Need 2 pixel wide sample so that ImageMagick does not return an empty image
		crop_info = json.loads(subprocess.check_output([ "convert", "%s[2x+%d+0]" % (png_filename, xoffset), "-trim", "json:-" ]))

		image_height = crop_info[0]["image"]["pageGeometry"]["height"]
		image_width = crop_info[0]["image"]["pageGeometry"]["width"]
		upper_baseline_y_from_top = crop_info[0]["image"]["pageGeometry"]["y"]
		lower_baseline_y_from_top = upper_baseline_y_from_top + crop_info[0]["image"]["geometry"]["height"]

		# Do not choose the exact average, but skewed closer to the lower
		# baseline
		baseline_y_from_top = round((upper_baseline_y_from_top + 7 * lower_baseline_y_from_top) / 8)
		return self._Baseline(image_width = image_width, image_height = image_height, upper = upper_baseline_y_from_top, lower = lower_baseline_y_from_top, mid = baseline_y_from_top)

	def render(self, property_dict):
		with tempfile.TemporaryDirectory(prefix = "pyradium_formula_") as tex_dir:
			# Formula to PDF first using pdflatex
			tex_filename = tex_dir + "/formula.tex"
			pdf_filename = tex_dir + "/formula.pdf"
			png_filename = tex_dir + "/formula.png"

			# Crop 3mm off the left side (1mm baseline bar + 2mm space)
			baseline = r"\rule{1mm}{1pt} \hspace{2mm}"
			left_crop_pixel = round((3 / 25.4) * self._rendering_dpi)
			left_crop_pixel_safe = round((2 / 25.4) * self._rendering_dpi)
			eval_baseline_at_x = round((0.5 / 25.4) * self._rendering_dpi)

			if property_dict.get("long", False):
				content = r"\[" + baseline + property_dict["formula"] + r" \]"
			else:
				content = r"$" + baseline + property_dict["formula"] + r"$"
			with open(tex_filename, "w") as tex_file:
				tex_file.write(_TEX_TEMPLATE % { "content": content })
			_log.debug("Rendering LaTeX formula: %s in directory %s", content, tex_dir)
			subprocess.check_call([ "pdflatex", "-output-directory=%s" % (tex_dir), tex_filename ], stdout = subprocess.DEVNULL)

			# Then render the PDF to PNG
			cmd = [ "convert", "-define", "profile:skip=ICC", "-density", str(self._rendering_dpi), "-trim", "+repage", pdf_filename, png_filename ]
			_log.debug("Converting PDF to PNG in %d dpi: %s", self._rendering_dpi, CmdlineEscape().cmdline(cmd))
			subprocess.check_call(cmd, stdout = subprocess.DEVNULL)

			_log.debug("Crop on left side: %d (choosing %d to be on safe side); evaluating baseline at x = %d; filename %s", left_crop_pixel, left_crop_pixel_safe, eval_baseline_at_x, png_filename)
			baseline = self._get_baseline_info(png_filename, eval_baseline_at_x)
			_log.debug("Baseline Y from top %d px upper, %d px lower, %d px mid (equals %d px mid from bottom)", baseline.upper, baseline.lower, baseline.mid, baseline.image_height - baseline.mid)

			# Then crop the image finally and capture cropping metadata along the way
			crop_meta = json.loads(subprocess.check_output([ "convert", "-crop", "+%d+0" % (left_crop_pixel_safe), "-trim", png_filename, "json:-" ]))[0]
			cmd = [ "convert", "-crop", "+%d+0" % (left_crop_pixel_safe), "-trim", "+repage", png_filename, "png:-" ]
			png_data = subprocess.check_output(cmd)
			_log.debug("Final crop to output size: %s", CmdlineEscape().cmdline(cmd))
			if self._DEBUG:
				with open(tex_dir + "/processed_01_crop_meta.json", "w") as f:
					json.dump(crop_meta, f, indent = 4, sort_keys = True)
				with open(tex_dir + "/processed_01_cropped.png", "wb") as f:
					f.write(png_data)

			_log.debug("Crop upper left corner is at %d, %d and cropped size is %d x %d px", crop_meta["image"]["pageGeometry"]["x"], crop_meta["image"]["pageGeometry"]["y"], crop_meta["image"]["geometry"]["width"], crop_meta["image"]["geometry"]["height"])

			# For debugging purposes, draw the baseline on the image
			if self._DEBUG:
				cmd = [ "convert", "-stroke", "red", "-draw", "line 0,%d %d,%d" % (baseline.mid, crop_meta["image"]["geometry"]["width"], baseline.mid) ]
				cmd += [ "-", "png:-" ]
				png_data = subprocess.check_output(cmd, input = png_data)
				with open(tex_dir + "/processed_02_baseline.png", "wb") as f:
					f.write(png_data)

			# Compute the shifted baseline in the cropped image
			baseline_from_top_cropped = baseline.mid - crop_meta["image"]["pageGeometry"]["y"]
			baseline_from_bottom_cropped = crop_meta["image"]["geometry"]["height"] - baseline_from_top_cropped
			_log.debug("Adapted baseline offsets for cropped image: %d px from top (equals %d px from bottom).", baseline_from_top_cropped, baseline_from_bottom_cropped)

			# Return an image object
			image = {
				"png_data":	png_data,
				"info": {
					"width": crop_meta["image"]["geometry"]["width"],
					"height": crop_meta["image"]["geometry"]["height"],
					"baseline": baseline_from_bottom_cropped,
				},
			}
			if self._DEBUG:
				input("Press RETURN to exit...")
			return image

if __name__ == "__main__":
	logging.basicConfig(format = " {name:>20s} [{levelname:.1s}]: {message}", style = "{", level = logging.DEBUG)

	from pyradium.RendererCache import RendererCache
	#renderer = RendererCache(LatexFormulaRenderer())
	renderer = LatexFormulaRenderer()
	#print(renderer.render({ "formula": "y^2 = x^3 + ax + b" }))
	#result = renderer.render({ "formula": r"\Gamma" })
	#result = renderer.render({ "formula": r"^{\circ}" })
	#result = renderer.render({ "formula": r"abcdefg" })
	#result = renderer.render({ "formula": r"_{\circ}" })
	#result = renderer.render({ "formula": r"\left( 1 + \frac{1}{2} \right)^{x^2 + \frac{10}{123}}" })
	result = renderer.render({ "formula": r"\left( 3 + \frac{1}{2} \right)^{\frac{10}{123}}" })		# REMOVE THIS BEFORE COMMITING
#	with open("out.png", "wb") as f:
#		f.write(result.data["png_data"])
