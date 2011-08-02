-- Quick launch bar widget BEGINS
function getValue(t, key)
   _, _, res = string.find(t, key .. " *= *([^%c]+)%c")
   return res
end

function split (s,t)
   local l = {n=0}
   local f = function (s)
		l.n = l.n + 1
		l[l.n] = s
	     end
   local p = "%s*(.-)%s*"..t.."%s*"
   s = string.gsub(s,p,f)
   l.n = l.n + 1
   return l
end

function quicklaunchbar()
   local launchbar = { layout = awful.widget.layout.horizontal.leftright }

   filedir = "/home/tansell/.config/awesome/quicklaunchbar/" -- Specify your folder with shortcuts here
   files = split(io.popen("ls " .. filedir .. "*.desktop"):read("*all"),"\n")
   for i = 1, table.getn(files) do
      local t = io.open(files[i]):read("*all")
      launchbar[i] = { image = image(getValue(t,"Icon")),
                            command = getValue(t,"Exec"),
                           position = tonumber(getValue(t,"Position")) or 255 }
   end

   table.sort(launchbar, function(a,b) return a.position < b.position end)
   for i = 1, table.getn(launchbar) do
      launchbar[i] = awful.widget.launcher(launchbar[i])
   end
   return launchbar
end
-- Quick launch bar widget END
