-- Quick launchbar widget for Awesome WM
-- http://awesome.naquadah.org/wiki/Quick_launch_bar_widget/3.5
-- Put into your awesome/ folder and add the following to rc.lua:
--   local launchbar = require('launchbar')
--   local mylb = launchbar("/path/to/directory/with/shortcuts")
-- Then add mylb to the wibox.
 
local layout = require("wibox.layout")
local util = require("awful.util")
local launcher = require("awful.widget.launcher")
 
local launchbar = {}
 
local function getValue(t, key)
   local _, _, res = string.find(t, key .. " *= *([^%c]+)%c")
   return res
end
 
local function find_icon(icon_name)
   if string.sub(icon_name, 1, 1) == '/' then
      if util.file_readable(icon_name) then
         return icon_name
      else
         return nil
      end
   end
 
   if launchbar.icon_dirs then
      for _, v in ipairs(launchbar.icon_dirs) do
         if util.file_readable(v .. "/" .. icon_name) then
            return v .. '/' .. icon_name
         end
      end
   end
   return nil
end
 
function launchbar.new(filedir)
   if not filedir then
      error("Launchbar: filedir was not specified")
   end
   local items = {}
   local widget = layout.fixed.horizontal()
   local files = io.popen("ls " .. filedir .. "*.desktop")
   for f in files:lines() do
      local t = io.open(f):read("*all")
      table.insert(items, { image = find_icon(getValue(t,"Icon")),
                            command = getValue(t,"Exec"),
                            position = tonumber(getValue(t,"Position")) or 255 })
   end
   table.sort(items, function(a,b) return a.position < b.position end)
   for _, v in ipairs(items) do
      if v.image then
         widget:add(launcher(v))
      end
   end
   return widget
end
 
return setmetatable(launchbar, { __call = function(_, ...) return launchbar.new(...) end })
