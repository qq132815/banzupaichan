# Read the file content
$content = Get-Content "templates\schedule.html" -Raw -Encoding UTF8

# Fix 1: Add orderProcessProgress variable declaration
$content = $content -replace "var currentTeamId=null, selectedOrder=null, editingId=null, currentPlan=null;", @"
var currentTeamId=null, selectedOrder=null, editingId=null, currentPlan=null;
var orderProcessProgress=[];
"@

# Fix 2: Reset orderProcessProgress in resetForm
$content = $content -replace "orderProcessProgress=\[\];", "orderProcessProgress=[];"

# Write back
$content | Set-Content "templates\schedule.html" -Encoding UTF8 -NoNewline
echo "Fixed schedule.html"
