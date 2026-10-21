r"""The streamed download's door to the network, for the tests that run the whole bootstrap.

scripts/bootstrap.ps1 fetches the archive and its checksum through one function, Get-DownloadResponse, and uses a
function of that name already in the session in its place, as it uses a function named Invoke-WebRequest in place of the
cmdlet. BRIDGE is that function for a whole-script run whose network is an Invoke-WebRequest stand-in: each request is
handed to the run's own stand-in - which writes down what it was asked and answers or fails as the case says, as it did
when the archive came through Invoke-WebRequest - and its answer becomes the response the streamed download reads.
Every check the bootstrap makes of a response (the hops, the host, the length) is the bootstrap's, outside this.
"""

BRIDGE = r"""
function global:Get-DownloadResponse {
    param($Request)
    $body = [IO.Path]::GetTempFileName()
    try {
        $answer = Invoke-WebRequest -Uri $Request.RequestUri.OriginalString -OutFile $body -UseBasicParsing -PassThru `
                                    -MaximumRedirection 5 -TimeoutSec ([int]($Request.Timeout / 1000))
    } catch {
        Remove-Item -LiteralPath $body -Force -ErrorAction SilentlyContinue
        throw
    }
    $response = New-Object psobject
    $response | Add-Member -MemberType NoteProperty -Name StatusCode -Value 200
    $response | Add-Member -MemberType NoteProperty -Name ResponseUri -Value $answer.BaseResponse.ResponseUri
    $response | Add-Member -MemberType NoteProperty -Name ContentLength -Value ([long](Get-Item -LiteralPath $body).Length)
    $response | Add-Member -MemberType NoteProperty -Name Headers -Value (New-Object Net.WebHeaderCollection)
    $response | Add-Member -MemberType NoteProperty -Name Body -Value $body
    $response | Add-Member -MemberType NoteProperty -Name Stream -Value $null
    $response | Add-Member -MemberType ScriptMethod -Name GetResponseStream -Value {
        $this.Stream = [IO.File]::OpenRead($this.Body)
        return $this.Stream
    }
    $response | Add-Member -MemberType ScriptMethod -Name Close -Value {
        if ($null -ne $this.Stream) { $this.Stream.Dispose() }
        Remove-Item -LiteralPath $this.Body -Force -ErrorAction SilentlyContinue
    }
    return $response
}
"""
