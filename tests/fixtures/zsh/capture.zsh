#!/usr/bin/env zsh
# Prints the completion candidates zsh offers for a command line, one per
# line as `word -- description` (or `word` without one); other text the
# completion prints is shown on lines starting with `! `.
#
#   zsh -f capture.zsh <fpath dir> '<command line>'
#
# Starts an interactive zsh under zpty, loads compinit with <fpath dir> first,
# replaces compadd with a version that prints what it would add, types the
# line, and presses Tab once.
zmodload zsh/zpty

zpty z zsh -f -i
local line

zpty -w z "fpath=(${(q)1} \$fpath)"
zpty -w z 'autoload -U compinit; compinit -u -d /dev/null'
zpty -w z 'compadd () {
  [[ ${@[1,(i)(-|--)]} == *-(O|A|D)\ * ]] && { builtin compadd "$@"; return $? }
  typeset -a __hits __dscr
  builtin compadd -A __hits "$@"
  (( $#__hits == 0 )) && return 1
  if (( $@[(I)-d] )); then
    __tmp=${@[$[${@[(i)-d]}+1]]}
    if [[ $__tmp == \(* ]]; then eval "__dscr=$__tmp"; else __dscr=( "${(@P)__tmp}" ); fi
  fi
  for i in {1..$#__hits}; do
    (( $#__dscr >= $i )) && dscr=" -- ${${${__dscr[$i]}##$__hits[$i] #}#-- }" || dscr=
    echo -E - "<<$__hits[$i]$dscr>>"
  done
}'
zpty -w z "zstyle ':completion:*' list-grouped false"
zpty -w z "zstyle ':completion:*' matcher-list ''"
zpty -w z "zstyle ':completion:*' insert-tab false"
zpty -w z "zstyle ':completion:*' completer _complete"
zpty -w z 'bindkey "^I" complete-word'
zpty -w z 'null-line () { echo -E - $'\''\0'\'' }'
zpty -w z 'compprefuncs=( null-line )'
zpty -w z 'comppostfuncs=( null-line exit )'

zpty -n -w z "$2"$'\t'

integer tog=0
# Everything between the two NUL lines is output of the completion.
while zpty -r z; do :; done | while IFS= read -r line; do
  if [[ $line == *$'\0\r' ]]; then
    (( tog++ )) && return 0 || continue
  fi
  (( tog )) || continue
  if [[ $line == *'<<'*'>>'* ]]; then
    line=${line#*<<}
    echo -E - ${line%>>*}
  else
    # Anything else printed during completion, such as a leaked error.
    line=${${line//$'\r'/}//[[:space:]]##/ }
    [[ $line == ' ' || -z $line ]] || echo -E - "! $line"
  fi
done
return 2
