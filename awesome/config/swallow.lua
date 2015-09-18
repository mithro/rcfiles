---------------------------------------------------------------------------
-- @author Tim 'mithro' Ansell
-- @copyright 2014, Tim 'mithro' Ansell
-- @release v0.0.1
-- vim: filetype=lua:expandtab:shiftwidth=4:tabstop=8:softtabstop=4:textwidth=80
---------------------------------------------------------------------------

local capi =
{
    awesome = awesome,
    root = root
}
local client = client
local wbase = require("wibox.widget.base")
local lbase = require("wibox.layout.base")
local aclient = require("awful.client")
local autil = require("awful.util")
local type = type
local setmetatable = setmetatable
local pairs = pairs
local error = error
local pcall = pcall
--local naughty = require("naughty")
local beautiful = require("beautiful")

-- wibox.widget.swallow
local swallow = { mt = {} }

--- Draw the given swallow on the given cairo context in the given geometry
function swallow:draw(wibox, cr, width, height)
    local x, y, _, _ = lbase.rect_to_device_geometry(cr, 0, 0, width, height)
    self.x = x
    self.y = y
    self.height = height
    --print("swallow:draw", self.c, width, height, self.x, self.y, self.height)
    self:update_client()
end

--- Fit the given swallow
function swallow:fit(width, height)
    --print("swallow:fit", self.c, width, height, self.width, self.height)
    if self.width and self.height then
        return self.width + beautiful.border_width*2, self.height
    else
        return 100, 1
    end
end

function swallow:update_client()
    if self.c then
        self.x_offset = screen[self.c.screen].geometry.x
        self.y_offset = screen[self.c.screen].geometry.y
        return self.c:geometry({x = self.x_offset+self.x+beautiful.border_width, y = self.y_offset+self.y, height = self.height})
    else
        self.x_offset = 0
        self.y_offset = 0
        return {x = 0, y = 0, height = 1, width = 1}
    end
end

function swallow:update_widget()
    local size = self:update_client()
    self.width = size.width
    --self.height = size.height
    self:emit_signal("widget::updated")
end

--- Set a swallow' text.
-- @param text The text to display. Pango markup is ignored and shown as-is.
function swallow:set_text(text)
    self._layout.text = text
end

local aclient_focusfilter = aclient.focus.filter
function focusfilter(c)
    --print("swallow:focusfilter")
    if c.class == "Gnome-panel" then
        return nil
    end
    return aclient_focusfilter(c)
end
aclient.focus.filter = focusfilter

function swallow:manage_window(c, startup)
    --print("swallow:manage_window", c, startup, c.class, self.c)
    if c.class == "Gnome-panel" then
        self.c = c
        aclient.floating.set(c, true)
        c['size_hints_honor'] = false
        c['skip_taskbar'] = true
        c['sticky'] = true
        c['focus'] = false
        c['border_width'] = 0

        c.focus = function()
            return nil
        end

        c:connect_signal("property::geometry", function()
            --local dim = self.c:geometry()
            --print("property::geometry", self.c, dim['x'], dim['y'], dim['height'], dim['width'])
            self:update_widget()
        end)

        c:connect_signal("unmanage", function(c)
            if self.c and c.window == self.c.window then
                self:unmanage_window()
            end
        end)

        self:emit_signal("widget::updated")
    end
end

function swallow:unmanage_window()
    --print("swallow:unmanage_window", self.c)
    self.c = nil
end

-- Returns a new swallow
local function new(widget_name)
    local ret = wbase.make_widget()

    for k, v in pairs(swallow) do
        if type(v) == "function" then
            ret[k] = v
        end
    end

    ret.x_offset = 0
    ret.y_offset = 0
    ret.x = 0
    ret.y = 0
    ret.height = 0

    client.connect_signal("manage", function (c, startup) 
        ret:manage_window(c, startup)
    end)

    ret:emit_signal("widget::updated")

    return ret
end

function swallow.mt:__call(...)
    return new(...)
end

return setmetatable(swallow, swallow.mt)

-- vim: filetype=lua:expandtab:shiftwidth=4:tabstop=8:softtabstop=4:textwidth=80
