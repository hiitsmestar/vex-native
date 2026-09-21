param(
  [Parameter(Position=0)][ValidateSet("ask","inspect","verify","reject","status")][string]$Action="status",
  [Parameter(Position=1)][string]$Value="",
  [string]$Context="",
  [ValidateSet("auto","fast","smart","deep")][string]$Tier="auto",
  [string]$Lesson="",
  [string]$Notes="",
  [string]$Reason=""
)
$py = "C:\Users\monte\Documents\VexNativeTools\VexCopilot.py"
switch ($Action) {
  "ask"     { & python $py ask $Value --context $Context --tier $Tier }
  "inspect" { if ($Value) { & python $py inspect --task-id $Value } else { & python $py inspect } }
  "verify"  { & python $py verify $Value --lesson $Lesson --notes $Notes }
  "reject"  { & python $py reject $Value --reason $Reason --notes $Notes }
  "status"  { & python $py status }
}
exit $LASTEXITCODE