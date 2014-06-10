

function string.ends(String,End)
   if not End then
     return false
   else
     return End=='' or string.sub(String,-string.len(End))==End
   end
end

function string.starts(String,Start)
   if not Start then
     return false
   else
     return string.sub(String,1,string.len(Start))==Start
   end
end
