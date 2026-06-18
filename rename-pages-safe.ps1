# rename-pages-safe.ps1 — без emoji, двухфазное переименование
$ErrorActionPreference = "Continue"
$Root  = "c:\csv_fix"
$Pages = Join-Path $Root "pages"

if (-not (Test-Path -LiteralPath $Pages)) {
    throw "Папка pages не найдена: $Pages"
}

function Safe-RenameFile {
    param(
        [Parameter(Mandatory = $true)][string]$FromName,
        [Parameter(Mandatory = $true)][string]$ToName
    )

    $fromPath = Join-Path $Pages $FromName
    $toPath   = Join-Path $Pages $ToName

    if (-not (Test-Path -LiteralPath $fromPath)) {
        Write-Warning "SKIP: источник не найден -> $FromName"
        return $false
    }

    if (Test-Path -LiteralPath $toPath) {
        Write-Warning "SKIP: цель уже существует -> $ToName"
        return $false
    }

    Rename-Item -LiteralPath $fromPath -NewName $ToName
    Write-Host "OK: $FromName -> $ToName"
    return $true
}

$Renames = [ordered]@{
    "05_Паспорт_месяца.py"                              = "10_Planning_Паспорт_месяца.py"
    "12_AI_Диагностика_плана.py"                        = "11_Planning_AI_Диагностика_плана.py"
    "14_Конструктор_месячного_плана.py"                  = "12_Planning_Конструктор_месячного_плана.py"
    "15_Контур_допуска_месячного_плана.py"              = "20_Admission_Контур_допуска_месячного_плана.py"
    "16_Управление_ограничениями_месячного_плана.py"     = "21_Admission_Управление_ограничениями_месячного_плана.py"
    "13_AI_Action_Engine.py"                            = "22_Admission_AI_Action_Engine.py"
    "06_Исполнение.py"                                  = "30_Execution_Исполнение.py"
    "07_Счётчик_звена.py"                               = "31_Execution_Счётчик_звена.py"
    "07_Качество_данных.py"                             = "32_Execution_Качество_данных.py"
    "08_Приемка_и_признание.py"                         = "40_Commercial_Приёмка_и_признание.py"
    "09_Контроль_потерь.py"                              = "41_Commercial_Контроль_потерь.py"
    "10_Экономика.py"                                   = "42_Commercial_Экономика.py"
    "11_Уведомления_заказчику.py"                       = "43_Commercial_Уведомления_заказчику.py"
    "12_AI_Агенты.py"                                   = "50_AI_Агенты.py"
}

Write-Host "=== War Room: emoji-файл -> ASCII ==="
Get-ChildItem -LiteralPath $Pages -Filter "*War_Room*.py" -File | ForEach-Object {
    if ($_.Name -ne "23_Admission_War_Room_ограничений.py") {
        Safe-RenameFile -FromName $_.Name -ToName "23_Admission_War_Room_ограничений.py" | Out-Null
    }
}

Write-Host "`n=== Фаза 1: временные имена ==="
foreach ($entry in $Renames.GetEnumerator()) {
    $from  = $entry.Key
    $final = $entry.Value
    $tmp   = "__renaming__$final"

    $fromPath = Join-Path $Pages $from
    if (-not (Test-Path -LiteralPath $fromPath)) { continue }
    if (Test-Path -LiteralPath (Join-Path $Pages $final)) {
        Write-Warning "SKIP phase1: финал уже есть -> $final"
        continue
    }
    Safe-RenameFile -FromName $from -ToName $tmp | Out-Null
}

Write-Host "`n=== Фаза 2: финальные имена ==="
Get-ChildItem -LiteralPath $Pages -Filter "__renaming__*.py" -File | ForEach-Object {
    $finalName = $_.Name.Substring("__renaming__".Length)
    Safe-RenameFile -FromName $_.Name -ToName $finalName | Out-Null
}

$WarRoomPath = Join-Path $Pages "23_Admission_War_Room_ограничений.py"
if (-not (Test-Path -LiteralPath $WarRoomPath)) {
    @'
import streamlit as st

st.set_page_config(layout="wide")

st.title("War Room ограничений")
st.caption("Совещания по ограничениям месячного плана — в разработке")

st.markdown(
    """
Страница будет использоваться для совещаний по ограничениям:
ТОП блокировок, просрочки, владельцы, стоимость под риском.

Пока без бизнес-логики.
"""
)
'@ | Set-Content -LiteralPath $WarRoomPath -Encoding UTF8
    Write-Host "CREATED: 23_Admission_War_Room_ограничений.py"
}

Write-Host "`n=== pages/ ==="
Get-ChildItem -LiteralPath $Pages -Filter "*.py" | Sort-Object Name | ForEach-Object { $_.Name }
