EAPI=7

if [[ "${PV}" == 9999 ]] ; then
	inherit vcs
fi

inherit pre-inherit
PRE_INHERIT_VAR="foo"

DESCRIPTION="Ebuild with misplaced pre-inherit eclass variable"
HOMEPAGE="https://github.com/pkgcore/pkgcheck"
SLOT="0"
LICENSE="BSD"

src_prepare() {
	default
	[[ ${PV} == 9999 ]] && vcs_public_function
}
