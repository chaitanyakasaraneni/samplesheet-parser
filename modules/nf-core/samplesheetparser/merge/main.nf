process SAMPLESHEETPARSER_MERGE {
    tag "$meta.id"
    label 'process_single'

    conda "${moduleDir}/environment.yml"
    container "${ workflow.containerEngine == 'singularity' && !task.ext.singularity_pull_docker_container ?
        'https://depot.galaxyproject.org/singularity/samplesheet-parser:1.2.0--pyhdfd78af_0' :
        'biocontainers/samplesheet-parser:1.2.0--pyhdfd78af_0' }"

    input:
    tuple val(meta), path(samplesheets)
    val target_version

    output:
    tuple val(meta), path("*.merged.csv"), emit: samplesheet
    tuple val(meta), path("*.merge.json"), emit: json
    path "versions.yml",                   emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def args   = task.ext.args   ?: ''
    def prefix = task.ext.prefix ?: "${meta.id}"
    if (!['v1', 'v2'].contains(target_version.toLowerCase())) {
        error "target_version must be 'v1' or 'v2', got: ${target_version}"
    }
    """
    samplesheet merge \\
        --to ${target_version} \\
        --output ${prefix}.merged.csv \\
        --format json \\
        ${args} \\
        ${samplesheets} > ${prefix}.merge.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        samplesheet-parser: \$(samplesheet --version | sed 's/samplesheet-parser //')
    END_VERSIONS
    """

    stub:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    touch ${prefix}.merged.csv
    echo '{"has_conflicts": false, "sample_count": 0, "conflicts": [], "warnings": []}' > ${prefix}.merge.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        samplesheet-parser: \$(samplesheet --version | sed 's/samplesheet-parser //')
    END_VERSIONS
    """
}
