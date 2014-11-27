---------------------------------------------------------------------------
-- @author Uli Schlachter
-- @author dodo
-- @copyright 2010, 2011 Uli Schlachter, dodo
-- @release v3.5.5
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
local naughty = require("naughty")
local beautiful = require("beautiful")

-- wibox.widget.swallow
local swallow = { mt = {} }

--- Draw the given swallow on the given cairo context in the given geometry
function swallow:draw(wibox, cr, width, height)
    local x, y, _, _ = lbase.rect_to_device_geometry(cr, 0, 0, width, height)
    self.x = x
    self.y = y
    self.height = height
    self:update_client()
end

--- Fit the given swallow
function swallow:fit(width, height)
    return self.width + beautiful.border_width*2, self.height
end

function swallow:update_client()
    if self.c then
        return self.c:geometry({x = self.x+beautiful.border_width, y = self.y, height = self.height})
    else
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
    if c.class == "Panel-test-applets" then
        return nil
    end
    return aclient_focusfilter(c)
end
aclient.focus.filter = focusfilter

function swallow:manage_window(c, startup)
    if startup then
        return
    end
--    if c.class == "Panel-test-applets" and c.name == self.widget_fullname then
    if c.pid == self.pid then
        self.c = c
        aclient.floating.set(c, true)
        c['size_hints_honor'] = false
        c['skip_taskbar'] = true
        c['sticky'] = true
        c['border_width'] = 0

        c.focus = function()
            return nil
        end

        self:update_widget()
        c:connect_signal("property::geometry", function()
            self:update_widget()
        end)
        c:connect_signal("unmanage", function(c)
            if self.c and c.window == self.c.window then
                self:unmanage_window()
            end
        end)
    end
end

function swallow:unmanage_window()
    self.c = nil
    self:update_widget()
    if self.pid then
        naughty.notify({text=string.format("%s crashed!", self.widget_fullname)})
        self.pid = nil
    end
    local cmd = string.format("panel-test-applets --iid %s --size xx-small --orient top --prefs-dir %s", self.widget_fullname, self.widget_prefs_dir)
    os.execute(string.format("pkill -f '%s'", cmd))
    self.pid, _ = autil.spawn(cmd, false)
end

function swallow:stopped(spawn_id, dont_warn)
    if spawn_id == self.spawn_id then
        self.pid = nil
    end
end

function swallow:exit()
    if self.pid then
        pcall(string.format("kill -9 %i", self.pid))
    end
end

-- Returns a new swallow
local function new(widget_name)
    local ret = wbase.make_widget()

    for k, v in pairs(swallow) do
        if type(v) == "function" then
            ret[k] = v
        end
    end

    ret.x = 0
    ret.y = 0
    ret.height = 0
    ret.widget_fullname = string.format("%sFactory::%s", widget_name, widget_name)
    ret.widget_prefs_dir = string.format("%s/widgets", autil.getdir("config"))
    ret.pid = nil

    client.connect_signal("manage", function (c, startup) 
        ret:manage_window(c, startup)
    end)
    capi.awesome.connect_signal("exit", function() 
        ret:exit()
    end)

    -- Start the app
    ret:unmanage_window()

    return ret
end

function swallow.mt:__call(...)
    return new(...)
end

return setmetatable(swallow, swallow.mt)

-- vim: filetype=lua:expandtab:shiftwidth=4:tabstop=8:softtabstop=4:textwidth=80
